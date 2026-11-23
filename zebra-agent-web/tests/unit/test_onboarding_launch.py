"""Onboarding launch, isolation and guardrails (#276).

Launch only the shipped built-in via ``create_library_process``; processes belong to no
user and never reach the owner's inbox; the wizard reads only its own process; no wizard
code creates users; LLM cost caps; idle expiry.
"""

from __future__ import annotations

import ast
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from zebra.core.models import ProcessState
from zebra.definitions.loader import load_definition
from zebra.forms import is_human_task
from zebra_agent.library import (
    BUILTIN_WORKFLOWS_DIR,
    SYSTEM_TAG,
    WorkflowLibrary,
    list_goal_workflows,
)
from zebra_agent_web.api import onboarding as ob

WEB = Path(ob.__file__).resolve().parents[1]
WIZARD_MODULES = [
    WEB / "api" / "onboarding.py",
    WEB / "api" / "onboarding_wizard_views.py",
    WEB / "api" / "onboarding_access.py",
    WEB / "api" / "onboarding_callback.py",
]


def _model(process_id):
    from zebra_agent_web.api.models import ProcessInstanceModel

    return ProcessInstanceModel.objects.get(id=process_id)


# ---------------------------------------------------------------------------
# The workflow
# ---------------------------------------------------------------------------


def test_every_visitor_step_stays_out_of_the_owner_inbox():
    definition = load_definition(BUILTIN_WORKFLOWS_DIR / "onboarding.yaml")
    steps = [td for td in definition.tasks.values() if not td.auto]
    # six steps and their retry screens, the access policy screen, and the instance wait
    # (#278) with its retry screen
    assert len(steps) == 15
    for td in steps:
        assert ob.is_visitor_task(td) or ob.is_callback_task(td)
        assert not is_human_task(td)
    waits = [td for td in steps if ob.is_callback_task(td)]
    assert [td.id for td in waits] == ["await_instance"]
    assert waits[0].properties["external"] == "onboarding_callback"


def test_each_step_says_what_happens_what_it_costs_and_how_to_undo():
    definition = load_definition(BUILTIN_WORKFLOWS_DIR / "onboarding.yaml")
    ordered = sorted(
        (td.properties["onboarding_order"], td.properties["onboarding_step"])
        for td in definition.tasks.values()
        if "onboarding_order" in td.properties
    )
    assert [step for _, step in ordered] == [
        "signup",
        "access",
        "provision",
        "verify",
        "commons",
        "contribute",
    ]
    for td in definition.tasks.values():
        if "onboarding_order" in td.properties:
            for key in ("what_happens", "cost", "undo"):
                assert td.properties[key].strip(), (td.id, key)


async def test_the_goal_selector_never_offers_onboarding(tmp_path):
    import shutil

    shutil.copy(BUILTIN_WORKFLOWS_DIR / "onboarding.yaml", tmp_path / "onboarding.yaml")
    library = WorkflowLibrary(tmp_path)
    [info] = await library.list_workflows()
    assert info.name == ob.WORKFLOW_NAME
    assert SYSTEM_TAG in info.tags
    assert await list_goal_workflows(library) == []


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_start_session_goes_through_the_choke_point(onboarding_env, monkeypatch):
    import zebra_tasks.launch as launch

    engine, library = onboarding_env
    entries = []
    real = launch.check_launch

    async def spy(definition, *, entry, **kwargs):
        entries.append((definition.name, entry))
        return await real(definition, entry=entry, **kwargs)

    monkeypatch.setattr(launch, "check_launch", spy)
    process, _nonce = await ob.start_session(engine, library)

    assert entries == [(ob.WORKFLOW_NAME, "onboarding")]
    assert process.state == ProcessState.RUNNING  # started at once: never a queued goal
    props = process.properties
    assert props[ob.MARKER_KEY] is True
    assert props["__cost_cap_usd__"] == pytest.approx(0.05)
    assert "__user_id__" not in props


@pytest.mark.django_db(transaction=True)
async def test_sessions_belong_to_no_user_even_when_someone_is_signed_in(onboarding_env):
    from asgiref.sync import sync_to_async
    from zebra_agent_web.middleware import _current_user_id_var

    engine, library = onboarding_env
    reset = _current_user_id_var.set(42)
    try:
        process, _ = await ob.start_session(engine, library)
    finally:
        _current_user_id_var.reset(reset)
    assert (await sync_to_async(_model)(process.id)).user_id is None


@pytest.mark.django_db(transaction=True)
async def test_a_modified_library_copy_is_never_started(onboarding_env):
    engine, library = onboarding_env
    [path] = (Path(library.library_path)).glob("onboarding*.yaml")
    path.write_text(path.read_text().replace("Your Oracle Cloud account", "Paste your API key"))
    library._cache.clear()

    with pytest.raises(ob.OnboardingRefused) as refused:
        await ob.start_session(engine, library)
    assert refused.value.status == 503
    assert await engine.store.get_processes_by_state(ProcessState.RUNNING) == []


def test_only_allowlisted_workflows_can_launch(tmp_path):
    with pytest.raises(ob.OnboardingRefused):
        ob.builtin_definition(WorkflowLibrary(tmp_path), "Agent Main Loop")


@pytest.mark.django_db(transaction=True)
async def test_live_session_cap(onboarding_env, settings):
    engine, library = onboarding_env
    settings.ZEBRA_AGENT_SETTINGS = {
        **settings.ZEBRA_AGENT_SETTINGS,
        "ONBOARDING_MAX_LIVE_SESSIONS": 2,
    }
    await ob.start_session(engine, library)
    await ob.start_session(engine, library)
    with pytest.raises(ob.OnboardingRefused, match="full"):
        await ob.start_session(engine, library)


# ---------------------------------------------------------------------------
# Cost caps (S2)
# ---------------------------------------------------------------------------


def _spend(process_id: str, cost: float, when: datetime | None = None) -> None:
    from zebra_agent_web.api.models import LLMSpendModel

    LLMSpendModel.objects.create(
        occurred_at=when or datetime.now(UTC), cost=cost, process_id=process_id, model="m"
    )


@pytest.mark.django_db(transaction=True)
async def test_daily_cap_refuses_new_sessions_and_onboarding_llm_calls(onboarding_env, settings):
    from asgiref.sync import sync_to_async

    engine, library = onboarding_env
    process, _ = await ob.start_session(engine, library)
    await sync_to_async(_spend)(process.id, 0.50, datetime.now(UTC) - timedelta(days=1))
    assert await ob.llm_guard(process) is None  # yesterday's spend does not count

    await sync_to_async(_spend)(process.id, 1.00)
    assert await ob.spent_today() == pytest.approx(1.00)
    assert "daily" in await ob.llm_guard(process)
    with pytest.raises(ob.OnboardingRefused, match="today"):
        await ob.start_session(engine, library)


@pytest.mark.django_db(transaction=True)
async def test_llm_guard_ignores_other_processes(onboarding_env):
    from types import SimpleNamespace

    from asgiref.sync import sync_to_async

    engine, library = onboarding_env
    process, _ = await ob.start_session(engine, library)
    await sync_to_async(_spend)(process.id, 5.0)
    assert await ob.llm_guard(SimpleNamespace(properties={"goal": "x"})) is None


@pytest.mark.django_db(transaction=True)
async def test_a_session_over_its_cap_fails_its_llm_call_without_spending(onboarding_env):
    """O5: the engine's LLM guard and the session cap refuse before the provider is called."""
    from types import SimpleNamespace

    from zebra_tasks.llm.client import LLMCostCapExceeded, get_llm, set_llm_factory

    engine, library = onboarding_env
    process, _ = await ob.start_session(engine, library)
    process.properties["__total_cost__"] = 0.05
    calls = []

    class Provider:
        model = "fake"

        async def complete(self, *args, **kwargs):
            calls.append(args)
            raise AssertionError("the provider must not be called")

    previous = set_llm_factory(lambda model: Provider())
    try:
        context = SimpleNamespace(process=process, extras={"__llm_guard__": ob.llm_guard})
        with pytest.raises(LLMCostCapExceeded, match="cost cap"):
            await get_llm("low", context).complete([])
    finally:
        set_llm_factory(previous)
    assert calls == []
    assert await ob.spent_today() == 0


# ---------------------------------------------------------------------------
# Idle expiry (S2)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_idle_sessions_expire_and_active_ones_stay(onboarding_env):
    from asgiref.sync import sync_to_async
    from zebra_agent_web.api.models import ProcessInstanceModel

    engine, library = onboarding_env
    idle, _ = await ob.start_session(engine, library)
    active, _ = await ob.start_session(engine, library)
    old = datetime.now(UTC) - timedelta(days=31)
    await sync_to_async(ProcessInstanceModel.objects.filter(id=idle.id).update)(updated_at=old)

    assert await ob.expire_idle_sessions(engine, force=True) == [idle.id]
    assert (await engine.store.load_process(idle.id)).state == ProcessState.FAILED
    assert "expired" in (await engine.store.load_process(idle.id)).properties["__error__"]
    assert (await engine.store.load_process(active.id)).state == ProcessState.RUNNING
    # throttled: a second call within the hour does nothing
    assert await ob.expire_idle_sessions(engine) == []


@pytest.mark.django_db(transaction=True)
async def test_the_daemon_tick_expires_idle_sessions(onboarding_env, monkeypatch):
    from zebra_agent_web.api import daemon

    called = []

    async def fake_expire(engine, **_):
        called.append(engine)
        return []

    monkeypatch.setattr(ob, "expire_idle_sessions", fake_expire)

    class Scheduler:
        async def pick_next(self):
            return None

    engine, _ = onboarding_env
    await daemon._tick(scheduler=Scheduler(), budget_manager=None, engine=engine, dry_run=True)
    assert called == [engine]


# ---------------------------------------------------------------------------
# Source scans: no user creation, no list queries in the wizard
# ---------------------------------------------------------------------------


def test_no_wizard_code_creates_a_user_or_reaches_passkeys():
    forbidden = re.compile(
        r"create_user|create_superuser|objects\.create\(|get_user_model|auth_views|"
        r"begin_register|complete_register|webauthn|login\("
    )
    for path in WIZARD_MODULES:
        source = path.read_text()
        assert not forbidden.search(source), f"{path.name}: {forbidden.search(source).group()}"
    templates = (WEB.parent / "templates" / "onboarding").rglob("*.html")
    for template in templates:
        assert "/auth/" not in template.read_text(), template


_LIST_CALLS = {
    "list_processes",
    "get_running_processes",
    "get_processes_by_state",
    "list_child_processes",
    "get_ready_tasks",
    "get_running_tasks",
    "list_definitions",
    "load_process_events",
}


def test_wizard_views_never_list_processes():
    """Stores fail open without a user: the wizard may only load its own process by id."""
    for path in WIZARD_MODULES:
        tree = ast.parse(path.read_text())
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert not called & _LIST_CALLS, f"{path.name} lists: {called & _LIST_CALLS}"
    # The only store reads in the views module are the session's own
    views = WIZARD_MODULES[1].read_text()
    assert "inbox_items" not in views and "WorkflowRunModel" not in views


@pytest.mark.django_db(transaction=True)
async def test_wizard_state_reads_only_its_own_process(onboarding_env, monkeypatch):
    engine, library = onboarding_env
    process, _ = await ob.start_session(engine, library)
    store = engine.store
    for name in _LIST_CALLS:
        if hasattr(store, name):

            async def refuse(*args, _name=name, **kwargs):
                raise AssertionError(f"wizard called {_name}")

            monkeypatch.setattr(store, name, refuse)
    state = await ob.wizard_state(store, process)
    assert state.current.key == "signup"
