"""Onboarding wizard sessions for anonymous visitors (#276, epic #275).

Any Zebra can host the "get your own Zebra" wizard, including one with real users and data,
so it is safe there by construction: no accounts, no tables, no secrets. See
``specs/onboarding-design.md``.

- **State** is one *Onboarding* engine process per visitor. Its properties are the session:
  ``__onboarding__`` marks it, ``__onboarding_nonce_sha256__`` holds the hash of the visitor's
  nonce, ``__cost_cap_usd__`` caps its LLM spend.
- **Resume token**: a ``django.core.signing`` token ``{p: process_id, n: nonce}`` in an
  HttpOnly cookie and a resume link. Resuming checks the signature (30 days), loads that one
  process by id and compares the nonce hash. A new link rotates the nonce.
- **No list queries**: with no signed-in user the stores fail open (unfiltered), so the wizard
  reads only ``load_process(id)``, its definition and its own tasks. The only cross-process
  reads are the counts and sums below (live sessions, today's spend, idle expiry), which
  return numbers or act on onboarding processes only and never reach a visitor.
- **Launch** goes through ``create_library_process(entry="onboarding")`` for an allowlisted
  workflow whose library content is the shipped built-in, then starts it at once (a CREATED
  process would be picked up as a queued goal).
- **Guardrails**: per-IP rate limits (Django cache), a live-session cap, a daily LLM cap over
  all sessions (``llm_guard``, the ``__llm_guard__`` engine extra) and idle expiry from the
  daemon tick (``expire_idle_sessions``).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import logging
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from zebra.core.models import ProcessState, TaskResult, TaskState
from zebra_tasks.launch import create_library_process
from zebra_tasks.llm.client import COST_CAP_KEY

from zebra_agent_web.middleware import _current_user_id_var

if TYPE_CHECKING:
    from zebra.core.engine import WorkflowEngine
    from zebra.core.models import ProcessDefinition, ProcessInstance, TaskDefinition
    from zebra.storage.base import StateStore
    from zebra_agent.library import WorkflowLibrary

logger = logging.getLogger(__name__)

WORKFLOW_NAME = "Onboarding"
#: The only workflows the wizard may start (later step children are added here).
ONBOARDING_WORKFLOWS = frozenset({WORKFLOW_NAME})
LAUNCH_ENTRY = "onboarding"
#: ``external`` value of a step the visitor completes (kept out of the owner's inbox).
VISITOR_EXTERNAL = "onboarding_visitor"
#: ``external`` value of the wait the new instance's callback completes (#278 S4).
CALLBACK_EXTERNAL = "onboarding_callback"
#: Where the session keeps ``sha256`` of its callback token (see ``onboarding_callback``).
CALLBACK_HASH_KEY = "__onboarding_cb_sha256__"
COOKIE_NAME = "zebra_onboarding"
TOKEN_SALT = "zebra.onboarding.resume"
MARKER_KEY = "__onboarding__"
NONCE_KEY = "__onboarding_nonce_sha256__"
PROBLEM_ROUTE = "problem"
PROBLEM_FIELD = "problem"

_DEFAULTS: dict[str, Any] = {
    "ENABLED": False,
    "SESSION_COST_CAP_USD": 0.05,
    "DAILY_COST_CAP_USD": 1.00,
    "SESSIONS_PER_IP_HOUR": 5,
    "REQUESTS_PER_IP_MINUTE": 60,
    "MAX_LIVE_SESSIONS": 200,
    "SESSION_IDLE_DAYS": 30,
    "CLIENT_IP_HEADER": "",
    "STACK_ZIP_URL": "",
    "STACK_ZIP_SHA256": "",
}

_LIVE_STATES = (ProcessState.CREATED.value, ProcessState.RUNNING.value)
_EXPIRY_INTERVAL_SECONDS = 3600
_last_expiry_check = 0.0
_LOCK_OWNER = "onboarding-web"


class OnboardingRefused(Exception):
    """A wizard request that must not go ahead; ``message`` is safe to show the visitor."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def config(name: str) -> Any:
    """An ``ONBOARDING_*`` setting from ``ZEBRA_AGENT_SETTINGS``, with its default."""
    return getattr(settings, "ZEBRA_AGENT_SETTINGS", {}).get(f"ONBOARDING_{name}", _DEFAULTS[name])


# ---------------------------------------------------------------------------
# The switch: env default (off) AND the owner's toggle
# ---------------------------------------------------------------------------


async def owner_switch() -> bool:
    """The owner's onboarding toggle (``SystemStateModel.onboarding_enabled``)."""
    from zebra_agent_web.api.models import SystemStateModel

    state, _ = await SystemStateModel.objects.aget_or_create(pk=1)
    return state.onboarding_enabled


async def set_owner_switch(enabled: bool) -> None:
    """Set the owner's onboarding toggle."""
    from zebra_agent_web.api.models import SystemStateModel

    state, _ = await SystemStateModel.objects.aget_or_create(pk=1)
    state.onboarding_enabled = enabled
    await state.asave(update_fields=["onboarding_enabled"])


async def is_enabled() -> bool:
    """True only while ``ZEBRA_ONBOARDING_ENABLED`` is on and the owner switched it on."""
    if not config("ENABLED"):
        return False
    try:
        return await owner_switch()
    except Exception:
        logger.warning("Could not read the onboarding switch; treating it as off", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Resume token
# ---------------------------------------------------------------------------


def new_nonce() -> str:
    """A fresh random nonce (32 bytes, URL-safe)."""
    return secrets.token_urlsafe(32)


def nonce_hash(nonce: str) -> str:
    """The SHA-256 hex digest stored on the process instead of the nonce."""
    return hashlib.sha256(nonce.encode()).hexdigest()


def max_age_seconds() -> int:
    """How long a resume token (and an idle session) lives."""
    return int(config("SESSION_IDLE_DAYS")) * 86400


def make_token(process_id: str, nonce: str) -> str:
    """A signed, timestamped resume token for *process_id* and *nonce*."""
    return signing.dumps({"p": process_id, "n": nonce}, salt=TOKEN_SALT)


def read_token(token: str | None) -> tuple[str, str] | None:
    """``(process_id, nonce)`` from a valid, unexpired token, else None."""
    if not token:
        return None
    try:
        data = signing.loads(token, salt=TOKEN_SALT, max_age=max_age_seconds())
    except signing.BadSignature:  # includes SignatureExpired
        return None
    if not isinstance(data, dict):
        return None
    process_id, nonce = data.get("p"), data.get("n")
    if not isinstance(process_id, str) or not isinstance(nonce, str) or not nonce:
        return None
    return process_id, nonce


async def load_session(store: StateStore, token: str | None) -> ProcessInstance | None:
    """The onboarding process *token* resumes, or None.

    Loads exactly one process, by id, and accepts it only if it is an onboarding process
    whose stored nonce hash matches the token's nonce.
    """
    parsed = read_token(token)
    if parsed is None:
        return None
    process_id, nonce = parsed
    process = await store.load_process(process_id)
    if process is None:
        return None
    props = process.properties or {}
    expected = props.get(NONCE_KEY)
    if not props.get(MARKER_KEY) or not isinstance(expected, str):
        return None
    if not hmac.compare_digest(expected, nonce_hash(nonce)):
        return None
    return process


async def _update_properties(store: StateStore, process_id: str, changes: dict[str, Any]) -> None:
    """Merge *changes* into one process's properties under its lock."""
    for _attempt in range(20):
        async with store.lock(process_id, _LOCK_OWNER, timeout_seconds=10) as acquired:
            if acquired:
                process = await store.load_process(process_id)
                if process is None:
                    raise OnboardingRefused("This session no longer exists.", 404)
                process.properties.update(changes)
                await store.save_process(process)
                return
        await asyncio.sleep(0.1)
    raise OnboardingRefused("The wizard is busy with this session; try again.", 409)


async def rotate_nonce(store: StateStore, process_id: str) -> str:
    """Give the session a new nonce; every earlier cookie and resume link stops working."""
    nonce = new_nonce()
    await _update_properties(store, process_id, {NONCE_KEY: nonce_hash(nonce)})
    return nonce


async def forget_session(engine: WorkflowEngine, process_id: str) -> None:
    """End the visitor's session: invalidate its token, then fail the process."""
    await rotate_nonce(engine.store, process_id)
    process = await engine.store.load_process(process_id)
    if process is not None and process.state.value in _LIVE_STATES:
        await engine.fail_process(process_id, "The visitor ended this onboarding session")


# ---------------------------------------------------------------------------
# Rate limits (Django cache: LocMem, one web process)
# ---------------------------------------------------------------------------


def client_ip(request: Any) -> str:
    """The visitor's IP: the trusted proxy header when configured, else ``REMOTE_ADDR``."""
    header = config("CLIENT_IP_HEADER")
    if header:
        value = (request.headers.get(header) or "").split(",")[0].strip()
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            pass
    return request.META.get("REMOTE_ADDR") or "unknown"


def allow(bucket: str, ip: str, limit: int, window_seconds: int) -> bool:
    """Count one hit for *ip* in *bucket*; False once more than *limit* in the window."""
    key = f"onboarding:rl:{bucket}:{hashlib.sha256(ip.encode()).hexdigest()[:32]}"
    cache.add(key, 0, window_seconds)
    try:
        count = cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, window_seconds)
        count = 1
    return count <= limit


def allow_request(ip: str) -> bool:
    """The per-IP request limit for every wizard view (60/minute by default)."""
    return allow("req", ip, int(config("REQUESTS_PER_IP_MINUTE")), 60)


def allow_new_session(ip: str) -> bool:
    """The per-IP new-session limit (5/hour by default)."""
    return allow("start", ip, int(config("SESSIONS_PER_IP_HOUR")), 3600)


# ---------------------------------------------------------------------------
# Counts over onboarding processes (numbers only; never shown per process)
# ---------------------------------------------------------------------------


def _definition_ids_sync() -> list[str]:
    from zebra_agent_web.api.models import ProcessDefinitionModel

    return list(
        ProcessDefinitionModel.objects.filter(name__in=ONBOARDING_WORKFLOWS).values_list(
            "id", flat=True
        )
    )


@sync_to_async(thread_sensitive=False)
def live_session_count() -> int:
    """How many onboarding processes are live (created or running)."""
    from zebra_agent_web.api.models import ProcessInstanceModel

    return ProcessInstanceModel.objects.filter(
        definition_id__in=_definition_ids_sync(), state__in=_LIVE_STATES
    ).count()


def _day_start(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


@sync_to_async(thread_sensitive=False)
def spent_today(now: datetime | None = None) -> float:
    """LLM spend of every onboarding process since 00:00 UTC, from the spend ledger."""
    from django.db.models import Sum

    from zebra_agent_web.api.models import LLMSpendModel, ProcessInstanceModel

    since = _day_start(now or datetime.now(UTC))
    process_ids = ProcessInstanceModel.objects.filter(
        definition_id__in=_definition_ids_sync()
    ).values("id")
    total = LLMSpendModel.objects.filter(
        occurred_at__gte=since, process_id__in=process_ids
    ).aggregate(total=Sum("cost"))["total"]
    return float(total or 0)


async def daily_cap_reached() -> bool:
    """True once today's onboarding LLM spend has reached ``ONBOARDING_DAILY_COST_CAP_USD``."""
    return await spent_today() >= float(config("DAILY_COST_CAP_USD"))


async def llm_guard(process: ProcessInstance) -> str | None:
    """The ``__llm_guard__`` engine extra: refuse onboarding LLM calls over the daily cap."""
    if not (process.properties or {}).get(MARKER_KEY):
        return None
    if await daily_cap_reached():
        return "Onboarding daily LLM cost cap reached"
    return None


@sync_to_async(thread_sensitive=False)
def _idle_session_ids(cutoff: datetime) -> list[str]:
    from zebra_agent_web.api.models import ProcessInstanceModel

    return list(
        ProcessInstanceModel.objects.filter(
            definition_id__in=_definition_ids_sync(),
            state__in=_LIVE_STATES,
            updated_at__lt=cutoff,
        ).values_list("id", flat=True)
    )


async def expire_idle_sessions(
    engine: WorkflowEngine, *, now: datetime | None = None, force: bool = False
) -> list[str]:
    """Fail onboarding sessions idle longer than ``ONBOARDING_SESSION_IDLE_DAYS``.

    Called from each daemon tick; does the work at most hourly unless *force*. Never raises.
    """
    global _last_expiry_check
    if not force and time.monotonic() - _last_expiry_check < _EXPIRY_INTERVAL_SECONDS:
        return []
    _last_expiry_check = time.monotonic()
    days = int(config("SESSION_IDLE_DAYS"))
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    expired: list[str] = []
    try:
        for process_id in await _idle_session_ids(cutoff):
            await engine.fail_process(
                process_id, f"Onboarding session expired after {days} days without progress"
            )
            expired.append(process_id)
    except Exception:
        logger.exception("[daemon:onboarding] Expiring idle onboarding sessions failed")
    if expired:
        logger.info("[daemon:onboarding] Expired %d idle onboarding session(s)", len(expired))
    return expired


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------


def builtin_definition(library: WorkflowLibrary, name: str) -> ProcessDefinition:
    """The allowlisted workflow *name*, only while the library's copy is the shipped built-in.

    A dream copy, Commons import or local edit has another content hash, so it is refused
    rather than started for an anonymous visitor.
    """
    from zebra_agent.provenance import try_content_sha256

    if name not in ONBOARDING_WORKFLOWS:
        raise OnboardingRefused("That workflow is not part of onboarding.", 403)
    try:
        content_hash, _ = try_content_sha256(library.get_workflow_yaml(name))
        definition = library.get_workflow(name)
    except ValueError as e:
        logger.error("Onboarding workflow %r is not installed: %s", name, e)
        raise OnboardingRefused("Onboarding is not available on this Zebra.", 503) from e
    if not content_hash or content_hash not in library.builtin_hashes():
        logger.error("Onboarding workflow %r is not the shipped built-in; refusing it", name)
        raise OnboardingRefused("Onboarding is not available on this Zebra.", 503)
    return definition


async def start_session(
    engine: WorkflowEngine, library: WorkflowLibrary
) -> tuple[ProcessInstance, str]:
    """Create and start one visitor's onboarding process; returns it and its nonce.

    The process belongs to no user (``user_id`` NULL), whoever is signed in.
    """
    if await live_session_count() >= int(config("MAX_LIVE_SESSIONS")):
        raise OnboardingRefused("The wizard is full right now; please try again later.", 503)
    if await daily_cap_reached():
        raise OnboardingRefused("The wizard has reached today's limit; try again tomorrow.", 503)
    definition = builtin_definition(library, WORKFLOW_NAME)
    nonce = new_nonce()
    properties = {
        MARKER_KEY: True,
        NONCE_KEY: nonce_hash(nonce),
        COST_CAP_KEY: float(config("SESSION_COST_CAP_USD")),
    }
    reset = _current_user_id_var.set(None)
    try:
        process = await create_library_process(
            engine, definition, entry=LAUNCH_ENTRY, properties=properties
        )
        process = await engine.start_process(process.id)
    finally:
        _current_user_id_var.reset(reset)
    logger.info("Onboarding session %s started", process.id)
    return process, nonce


# ---------------------------------------------------------------------------
# The wizard's view of one process
# ---------------------------------------------------------------------------


@dataclass
class StepView:
    """One wizard step as the visitor sees it."""

    key: str
    title: str
    order: int
    state: str  # done | current | failed | locked
    what_happens: str = ""
    cost: str = ""
    undo: str = ""


@dataclass
class WizardState:
    """Everything the wizard page shows for one session."""

    process_id: str
    status: str  # active | waiting | finished | ended
    steps: list[StepView] = field(default_factory=list)
    task_id: str | None = None
    task_def: TaskDefinition | None = None
    schema: dict[str, Any] = field(default_factory=dict)
    routes: list[str] = field(default_factory=list)
    retry: bool = False
    ended_reason: str = ""
    #: Extra content the step shows (``onboarding_panel``: access, policy, provision, await)
    panel: str = ""
    #: The READY ``external: onboarding_callback`` wait while the session waits on its instance
    waiting_task_id: str | None = None

    @property
    def current(self) -> StepView | None:
        return next((s for s in self.steps if s.state in ("current", "failed")), None)


def is_visitor_task(task_def: Any) -> bool:
    """A step the anonymous visitor completes (and nothing else is)."""
    props = getattr(task_def, "properties", None) or {}
    return (
        not task_def.auto
        and props.get("external") == VISITOR_EXTERNAL
        and bool(props.get("onboarding_step"))
    )


def is_callback_task(task_def: Any) -> bool:
    """The wait the new instance's callback completes (never completed by the step form)."""
    props = getattr(task_def, "properties", None) or {}
    return (
        task_def is not None
        and not task_def.auto
        and props.get("external") == CALLBACK_EXTERNAL
        and bool(props.get("onboarding_step"))
    )


def _step_schema(task_def: TaskDefinition, process_properties: dict[str, Any]) -> dict[str, Any]:
    from zebra.forms import resolve_schema_templates, resolve_task_schema

    schema = resolve_task_schema(task_def.properties.get("schema"), process_properties) or {
        "type": "object",
        "properties": {},
    }
    return resolve_schema_templates(schema, process_properties)


def _routes(definition: ProcessDefinition, task_def_id: str) -> list[str]:
    from zebra.forms import get_routes_from_definition

    routings = [
        {"from": r.source_task_id, "to": r.dest_task_id, "condition": r.condition, "name": r.name}
        for r in definition.routings
    ]
    return get_routes_from_definition(task_def_id, routings)


async def wizard_state(store: StateStore, process: ProcessInstance) -> WizardState:
    """The step list and current step of *process*: only its own definition and tasks."""
    definition = await store.load_definition(process.definition_id)
    if definition is None:
        return WizardState(process.id, "ended", ended_reason="This session can't be shown.")
    ordered = sorted(
        (
            (int(td.properties["onboarding_order"]), task_id, td)
            for task_id, td in definition.tasks.items()
            if "onboarding_order" in (td.properties or {})
        ),
        key=lambda item: item[0],
    )
    state = WizardState(process.id, "active")
    current_key = None
    if process.state == ProcessState.COMPLETE:
        state.status = "finished"
    elif process.state in (ProcessState.FAILED,):
        state.status = "ended"
        state.ended_reason = str((process.properties or {}).get("__error__") or "")
    else:
        tasks = await store.load_tasks_for_process(process.id)
        ready = [
            t
            for t in tasks
            if t.state == TaskState.READY
            and is_visitor_task(definition.tasks.get(t.task_definition_id))
        ]
        if ready:
            task = ready[0]
            task_def = definition.tasks[task.task_definition_id]
            current_key = task_def.properties["onboarding_step"]
            state.task_id = task.id
            state.task_def = task_def
            state.retry = bool(task_def.properties.get("onboarding_retry"))
            state.schema = _step_schema(task_def, process.properties or {})
            state.routes = _routes(definition, task.task_definition_id)
            state.panel = str(task_def.properties.get("onboarding_panel") or "")
        else:
            state.status = "waiting"
            waiting = [
                t
                for t in tasks
                if t.state == TaskState.READY
                and is_callback_task(definition.tasks.get(t.task_definition_id))
            ]
            if waiting:
                task_def = definition.tasks[waiting[0].task_definition_id]
                current_key = task_def.properties["onboarding_step"]
                state.waiting_task_id = waiting[0].id
                state.panel = str(task_def.properties.get("onboarding_panel") or "")
    reached = state.status == "finished"
    current_order = next(
        (order for order, _id, td in ordered if td.properties["onboarding_step"] == current_key),
        None,
    )
    for order, _task_id, td in ordered:
        props = td.properties
        if reached:
            step_state = "done"
        elif current_order is None:
            step_state = "locked"
        elif order < current_order:
            step_state = "done"
        elif order == current_order:
            step_state = "failed" if state.retry else "current"
        else:
            step_state = "locked"
        state.steps.append(
            StepView(
                key=props["onboarding_step"],
                title=td.name,
                order=order,
                state=step_state,
                what_happens=str(props.get("what_happens", "")),
                cost=str(props.get("cost", "")),
                undo=str(props.get("undo", "")),
            )
        )
    return state


# ---------------------------------------------------------------------------
# Submitting a step
# ---------------------------------------------------------------------------

#: Private material no wizard form may ever accept (threat model T4).
_PRIVATE_MATERIAL = [
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),  # OpenRouter / OpenAI-style API keys
    re.compile(r"\bnsec1[02-9ac-hj-np-z]{20,}"),  # Nostr / Commons secret keys
]
PRIVATE_MATERIAL_ERROR = (
    "This looks like a private key or secret. Never paste keys here: the wizard does not need them."
)


def find_private_material(value: Any) -> bool:
    """True if *value* (any JSON value) contains something that looks like a secret."""
    if isinstance(value, str):
        return any(p.search(value) for p in _PRIVATE_MATERIAL)
    if isinstance(value, dict):
        return any(find_private_material(v) for v in value.values())
    if isinstance(value, list):
        return any(find_private_material(v) for v in value)
    return False


def _editable_fields(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        name: spec
        for name, spec in (schema.get("properties") or {}).items()
        if isinstance(spec, dict) and not spec.get("readOnly")
    }


def step_output(
    state: WizardState, raw: dict[str, Any], route: str | None
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Validate a submitted step; returns ``(output, field_errors)``.

    The "problem" route keeps only the visitor's description of what went wrong. Any other
    route validates the schema (a required checkbox must be ticked) and drops ``problem``.
    Fields not in the schema, and read-only ones, are ignored. Nothing that looks like a
    private key or secret is accepted.
    """
    from zebra.forms import coerce_form_data, validate_form_data

    fields = _editable_fields(state.schema)
    flat = {k: v for k, v in raw.items() if k in fields}
    errors: dict[str, list[str]] = {}
    if route == PROBLEM_ROUTE:
        problem = str(flat.get(PROBLEM_FIELD) or "").strip()
        if not problem:
            errors[PROBLEM_FIELD] = ["Tell us what went wrong, so the next screen can show it."]
        output = {PROBLEM_FIELD: problem}
    else:
        schema = {
            **state.schema,
            "properties": {k: v for k, v in fields.items() if k != PROBLEM_FIELD},
        }
        flat.pop(PROBLEM_FIELD, None)
        output = coerce_form_data(schema, flat)
        for error in validate_form_data(schema, output):
            errors.setdefault(error.field, []).append(error.message)
        for name in schema.get("required") or []:
            spec = fields.get(name) or {}
            if spec.get("type") == "boolean" and output.get(name) is not True:
                errors.setdefault(name, []).append("Tick this to continue.")
    for name, value in output.items():
        if find_private_material(value):
            errors.setdefault(name, []).append(PRIVATE_MATERIAL_ERROR)
    return output, errors


async def submit_step(
    engine: WorkflowEngine,
    process: ProcessInstance,
    task_id: str,
    raw: dict[str, Any],
    route: str | None,
) -> dict[str, list[str]]:
    """Complete the visitor's current step; returns field errors (empty on success).

    Only the session's own READY visitor task can be completed, and only by a route it has.
    """
    state = await wizard_state(engine.store, process)
    if state.waiting_task_id is not None and task_id == state.waiting_task_id:
        # While it waits on the instance the visitor can only report that something went wrong
        if route != PROBLEM_ROUTE:
            raise OnboardingRefused("Choose one of the step's buttons.", 400)
        state.task_id = task_id
        state.routes = [PROBLEM_ROUTE]
        state.schema = {"type": "object", "properties": {PROBLEM_FIELD: {"type": "string"}}}
    if state.task_id is None or state.task_id != task_id:
        raise OnboardingRefused("This step has already moved on; here is where you are now.", 409)
    if (
        state.task_def is not None
        and state.task_def.properties.get("onboarding_needs_token")
        and route != PROBLEM_ROUTE
        and not (process.properties or {}).get(CALLBACK_HASH_KEY)
    ):
        return {"applied": ["Make your one-time token first and paste it into the stack."]}
    if state.routes:
        if route not in state.routes:
            raise OnboardingRefused("Choose one of the step's buttons.", 400)
    else:
        route = None
    output, errors = step_output(state, raw, route)
    if errors:
        return errors
    reset = _current_user_id_var.set(None)
    try:
        await engine.complete_task(
            task_id, TaskResult(success=True, output=output, next_route=route)
        )
    finally:
        _current_user_id_var.reset(reset)
    return {}
