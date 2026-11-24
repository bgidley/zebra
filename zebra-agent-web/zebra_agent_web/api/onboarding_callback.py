"""The host side of the onboarding callback (#278, slice S4; instance side in #279 S5).

A new Zebra, built in the visitor's own tenancy, calls home once on first boot to say where it
is. The protocol (``specs/onboarding-design.md`` section 4):

1. The visitor makes a one-time callback token ``cb`` on the provision step (32 random bytes,
   base64url, 43 characters). It is shown once and pasted into the stack variable
   ``onboarding_token``. The process stores only ``sha256(cb)`` (hex), its expiry (1 hour) and
   a used flag. A new token rotates the old one.
2. The instance posts ``{token, instance_url, version, commons_fingerprint?}`` to
   ``POST /onboarding/callback/``.
3. The host looks the session up by token hash (cache, then a scan of RUNNING onboarding
   processes), checks expiry and the used flag, then proves the instance controls the URL:
   ``GET <instance_url>/.well-known/zebra-onboarding`` must return ``sha256(cb)`` as lowercase
   hex. The fetch is https on port 443 to a public IP only (every DNS answer is checked, then
   the connection is pinned to a checked IP), never follows a redirect, and gives up after 5 s
   or 4 KB.
4. On success the token is marked used (compare-and-set under the process lock) and the
   ``await_instance`` wait (``external: onboarding_callback``) completes with non-secret
   outputs. Any failure leaves the token unused until it expires.

The token itself is never stored or logged.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import re
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx
from asgiref.sync import sync_to_async
from django.core.cache import cache
from zebra.core.models import ProcessState, TaskResult, TaskState

from zebra_agent_web.api import onboarding as ob
from zebra_agent_web.middleware import _current_user_id_var

if TYPE_CHECKING:
    from zebra.core.engine import WorkflowEngine
    from zebra.core.models import ProcessInstance
    from zebra.storage.base import StateStore

logger = logging.getLogger(__name__)

#: ``external`` value of the wait the callback completes.
CALLBACK_EXTERNAL = ob.CALLBACK_EXTERNAL
HASH_KEY = ob.CALLBACK_HASH_KEY
EXPIRES_KEY = "__onboarding_cb_expires__"
USED_KEY = "__onboarding_cb_used__"
TOKEN_TTL = timedelta(hours=1)
WELL_KNOWN_PATH = "/.well-known/zebra-onboarding"
FETCH_TIMEOUT_SECONDS = 5.0
FETCH_MAX_BYTES = 4096
REQUEST_MAX_BYTES = 4096
CALLBACKS_PER_IP_MINUTE = 10
_CACHE_PREFIX = "onboarding:cb:"

_TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_VERSION = re.compile(r"^[0-9A-Za-z.+_-]{1,64}$")
_FINGERPRINT = re.compile(r"^(?:[0-9a-f]{64}|npub1[02-9ac-hj-np-z]{58})$")
_HOSTNAME = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class CallbackError(Exception):
    """A callback that must not go ahead; ``message`` is safe to return to the caller."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.message = message
        self.status = status


def token_hash(token: str) -> str:
    """``sha256(token)`` as lowercase hex: what the host stores and the instance serves."""
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# The token
# ---------------------------------------------------------------------------


async def issue_token(store: StateStore, process_id: str) -> str:
    """A new one-time callback token for the session; rotates (invalidates) any earlier one.

    Returns the token, which the caller shows to the visitor once; only its hash is kept.
    """
    token = secrets.token_urlsafe(32)
    digest = token_hash(token)
    expires = _now() + TOKEN_TTL
    await ob._update_properties(
        store,
        process_id,
        {HASH_KEY: digest, EXPIRES_KEY: expires.isoformat(), USED_KEY: False},
    )
    cache.set(_CACHE_PREFIX + digest, process_id, int(TOKEN_TTL.total_seconds()))
    return token


@dataclass(frozen=True)
class TokenStatus:
    """The session's callback token, as far as the wizard may show it."""

    exists: bool
    used: bool
    expired: bool
    expires_at: str

    @property
    def live(self) -> bool:
        return self.exists and not self.used and not self.expired


def token_status(properties: dict[str, Any], now: datetime | None = None) -> TokenStatus:
    """Whether *properties* hold a callback token and whether it can still be used."""
    digest = properties.get(HASH_KEY)
    if not isinstance(digest, str):
        return TokenStatus(False, False, False, "")
    expires_raw = str(properties.get(EXPIRES_KEY) or "")
    try:
        expires = datetime.fromisoformat(expires_raw)
    except ValueError:
        return TokenStatus(True, bool(properties.get(USED_KEY)), True, "")
    return TokenStatus(
        True, bool(properties.get(USED_KEY)), (now or _now()) >= expires, expires_raw
    )


def _token_matches(properties: dict[str, Any], digest: str) -> bool:
    stored = properties.get(HASH_KEY)
    return isinstance(stored, str) and hmac.compare_digest(stored, digest)


@sync_to_async(thread_sensitive=False)
def _scan_running_sessions(digest: str) -> str | None:
    """The RUNNING onboarding process holding *digest* (cache miss: e.g. after a restart)."""
    from zebra_agent_web.api.models import ProcessInstanceModel

    rows = ProcessInstanceModel.objects.filter(
        definition_id__in=ob._definition_ids_sync(), state=ProcessState.RUNNING.value
    ).values_list("id", "properties")
    for process_id, raw in rows.iterator():
        try:
            props = json.loads(raw or "{}")
        except ValueError:
            continue
        if isinstance(props, dict) and _token_matches(props, digest):
            return process_id
    return None


async def find_session(store: StateStore, digest: str) -> ProcessInstance | None:
    """The running onboarding session whose current token hash is *digest*, else None."""
    process_id = cache.get(_CACHE_PREFIX + digest) or await _scan_running_sessions(digest)
    if not process_id:
        return None
    process = await store.load_process(process_id)
    if process is None or process.state != ProcessState.RUNNING:
        return None
    props = process.properties or {}
    if not props.get(ob.MARKER_KEY) or not _token_matches(props, digest):
        return None  # rotated: the cache still points here, but the token is gone
    return process


# ---------------------------------------------------------------------------
# SSRF-guarded control proof
# ---------------------------------------------------------------------------

Resolver = Callable[[str], Awaitable[list[str]]]


def normalize_instance_url(raw: object) -> str:
    """``https://<host>`` from *raw*, or raise ``CallbackError(400)``.

    Only an https origin on port 443 is accepted: no user info, path, query or fragment.
    """
    if not isinstance(raw, str) or not raw or len(raw) > 300:
        raise CallbackError("instance_url must be an https URL.", 400)
    try:
        parts = urlsplit(raw.strip())
        port = parts.port
    except ValueError as e:
        raise CallbackError("instance_url is not a valid URL.", 400) from e
    if parts.scheme != "https":
        raise CallbackError("instance_url must use https.", 400)
    if parts.username is not None or parts.password is not None:
        raise CallbackError("instance_url must not contain credentials.", 400)
    if port not in (None, 443):
        raise CallbackError("instance_url must use port 443.", 400)
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise CallbackError(
            "instance_url must be just the origin, e.g. https://zebra.example.", 400
        )
    host = (parts.hostname or "").rstrip(".").lower()
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if not _HOSTNAME.match(host):
            raise CallbackError("instance_url has an invalid host name.", 400) from None
        return f"https://{host}"
    if not is_public_ip(ip):
        raise CallbackError("instance_url must be a public address.", 400)
    return f"https://[{ip}]" if ip.version == 6 else f"https://{ip}"


def is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True only for a globally routable unicast address (not private, loopback, link-local,
    CGNAT, multicast, reserved or unspecified; IPv4-mapped and 6to4/Teredo forms unwrapped)."""
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = ip.ipv4_mapped or ip.sixtofour or (ip.teredo[1] if ip.teredo else None)
        if embedded is not None:
            return is_public_ip(embedded)
        if ip.is_site_local:  # deprecated fec0::/10, which is_global still counts as global
            return False
    return bool(ip.is_global) and not (
        ip.is_multicast or ip.is_reserved or ip.is_unspecified or ip.is_link_local
    )


async def system_resolver(host: str) -> list[str]:
    """Every address *host* resolves to on port 443 (TCP)."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, 443, type=0, proto=6)
    return sorted({info[4][0] for info in infos})


async def resolve_public(host: str, resolver: Resolver | None = None) -> str:
    """One public IP for *host*; ``CallbackError(422)`` if any answer is not public.

    Refusing a host with *any* private answer stops mixed answers and DNS tricks; the caller
    then connects to the returned IP, so a second lookup (rebinding) cannot change the target.
    """
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    else:
        if not is_public_ip(ip):
            raise CallbackError("The instance address is not public.", 422)
        return str(ip)
    try:
        answers = await (resolver or system_resolver)(host)
    except (OSError, UnicodeError) as e:
        raise CallbackError("The instance host name does not resolve.", 422) from e
    if not answers:
        raise CallbackError("The instance host name does not resolve.", 422)
    ips = []
    for answer in answers:
        try:
            ip = ipaddress.ip_address(answer.split("%", 1)[0])
        except ValueError as e:
            raise CallbackError("The instance host name does not resolve.", 422) from e
        if not is_public_ip(ip):
            raise CallbackError("The instance host name resolves to a non-public address.", 422)
        ips.append(ip)
    return str(ips[0])


async def fetch_challenge(
    instance_url: str,
    *,
    resolver: Resolver | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float = FETCH_TIMEOUT_SECONDS,
    max_bytes: int = FETCH_MAX_BYTES,
) -> str:
    """The body of ``<instance_url>/.well-known/zebra-onboarding``, under the SSRF guards.

    *instance_url* must come from ``normalize_instance_url``. Raises ``CallbackError(422)`` for
    a non-public target, a redirect or any non-200 status, a body over *max_bytes*, a response
    slower than *timeout* seconds overall, or a TLS / connection failure.
    """
    origin = normalize_instance_url(instance_url)
    host = urlsplit(origin).hostname or ""
    try:
        async with asyncio.timeout(timeout):
            ip = await resolve_public(host, resolver)
            ip_host = f"[{ip}]" if ":" in ip else ip
            async with httpx.AsyncClient(
                transport=transport,
                follow_redirects=False,
                trust_env=False,  # never through a configured proxy
                timeout=timeout,
                verify=True,
            ) as client:
                async with client.stream(
                    "GET",
                    f"https://{ip_host}{WELL_KNOWN_PATH}",
                    headers={
                        "Host": host,
                        "Accept": "text/plain",
                        "Accept-Encoding": "identity",  # the cap counts bytes on the wire
                        "User-Agent": "zebra-onboarding",
                    },
                    extensions={"sni_hostname": host},
                ) as response:
                    if response.status_code != 200:
                        raise CallbackError(
                            f"The instance answered {response.status_code}, not 200.", 422
                        )
                    body = bytearray()
                    async for chunk in response.aiter_raw():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            raise CallbackError("The instance's answer is too large.", 422)
    except TimeoutError as e:
        raise CallbackError("The instance did not answer in time.", 422) from e
    except httpx.HTTPError as e:
        raise CallbackError("Could not reach the instance over https.", 422) from e
    return body.decode("utf-8", errors="replace")


async def verify_control(
    instance_url: str, digest: str, *, resolver: Resolver | None = None, **fetch: Any
) -> None:
    """Raise ``CallbackError(422)`` unless the instance serves *digest* at the well-known URL."""
    body = (await fetch_challenge(instance_url, resolver=resolver, **fetch)).strip().lower()
    if not _HEX64.match(body) or not hmac.compare_digest(body, digest):
        raise CallbackError("The instance did not prove it holds this token.", 422)


# ---------------------------------------------------------------------------
# Completing the wait
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CallbackRequest:
    """A validated callback body (the token is kept only in memory)."""

    token: str
    instance_url: str
    version: str
    commons_fingerprint: str


def parse_request(body: bytes) -> CallbackRequest:
    """Validate a callback body; ``CallbackError(400)`` (``413`` when too large)."""
    if len(body) > REQUEST_MAX_BYTES:
        raise CallbackError("Request too large.", 413)
    try:
        data = json.loads(body or b"null")
    except ValueError as e:
        raise CallbackError("Send a JSON object.", 400) from e
    if not isinstance(data, dict):
        raise CallbackError("Send a JSON object.", 400)
    token = data.get("token")
    if not isinstance(token, str) or not _TOKEN.match(token):
        raise CallbackError("token must be the 43-character token from the wizard.", 400)
    version = data.get("version", "")
    if version and (not isinstance(version, str) or not _VERSION.match(version)):
        raise CallbackError("version is not a version string.", 400)
    fingerprint = data.get("commons_fingerprint") or ""
    if fingerprint and (not isinstance(fingerprint, str) or not _FINGERPRINT.match(fingerprint)):
        raise CallbackError("commons_fingerprint must be a public key (hex or npub).", 400)
    return CallbackRequest(
        token=token,
        instance_url=normalize_instance_url(data.get("instance_url")),
        version=version or "",
        commons_fingerprint=fingerprint,
    )


async def _waiting_task_id(store: StateStore, process: ProcessInstance) -> str | None:
    """The session's READY ``external: onboarding_callback`` task, if it is waiting on one."""
    definition = await store.load_definition(process.definition_id)
    if definition is None:
        return None
    for task in await store.load_tasks_for_process(process.id):
        task_def = definition.tasks.get(task.task_definition_id)
        props = (task_def.properties if task_def else None) or {}
        if task.state == TaskState.READY and props.get("external") == CALLBACK_EXTERNAL:
            return task.id
    return None


async def _claim_token(store: StateStore, process_id: str, digest: str) -> None:
    """Mark the token used, only if it is still this session's live token (else 410).

    Store locks are re-entrant per owner, so each claim takes the lock under its own owner
    name: two concurrent callbacks must not both hold it.
    """
    owner = f"{ob._LOCK_OWNER}:claim:{secrets.token_hex(8)}"
    for _attempt in range(20):
        async with store.lock(process_id, owner, timeout_seconds=10) as acquired:
            if acquired:
                process = await store.load_process(process_id)
                props = (process.properties if process else None) or {}
                if not _token_matches(props, digest) or not token_status(props).live:
                    raise CallbackError("This token is no longer valid.", 410)
                props[USED_KEY] = True
                await store.save_process(process)
                return
        await asyncio.sleep(0.1)
    raise CallbackError("Busy; try again.", 409)


async def complete_with_instance(
    engine: WorkflowEngine,
    process: ProcessInstance,
    digest: str,
    instance_url: str,
    *,
    version: str = "",
    commons_fingerprint: str = "",
    via: str = "callback",
    resolver: Resolver | None = None,
    **fetch: Any,
) -> dict[str, Any]:
    """Prove control of *instance_url*, claim the token and complete the session's wait.

    Shared by the instance's callback and the visitor's manual-paste fallback. Returns the
    task output. Raises ``CallbackError``: 410 token not live, 409 the session is not waiting
    on the instance yet, 422 the control proof failed (the token stays unused).
    """
    store = engine.store
    if not token_status(process.properties or {}).live:
        raise CallbackError("This token is no longer valid.", 410)
    task_id = await _waiting_task_id(store, process)
    if task_id is None:
        raise CallbackError("This session is not waiting for its instance yet; retry later.", 409)
    await verify_control(instance_url, digest, resolver=resolver, **fetch)
    await _claim_token(store, process.id, digest)
    output = {
        "instance_url": instance_url,
        "version": version,
        "commons_fingerprint": commons_fingerprint,
        "verified_at": _now().isoformat(),
        "via": via,
    }
    reset = _current_user_id_var.set(None)
    try:
        await engine.complete_task(
            task_id, TaskResult(success=True, output=output, next_route="done")
        )
    finally:
        _current_user_id_var.reset(reset)
    cache.delete(_CACHE_PREFIX + digest)
    logger.info("Onboarding session %s: instance verified via %s", process.id, via)
    return output


async def handle_callback(
    engine: WorkflowEngine, body: bytes, *, resolver: Resolver | None = None, **fetch: Any
) -> dict[str, Any]:
    """``POST /onboarding/callback/``: validate, look up by token hash, verify, complete."""
    request = parse_request(body)
    digest = token_hash(request.token)
    process = await find_session(engine.store, digest)
    if process is None:
        raise CallbackError("This token is no longer valid.", 410)
    return await complete_with_instance(
        engine,
        process,
        digest,
        request.instance_url,
        version=request.version,
        commons_fingerprint=request.commons_fingerprint,
        via="callback",
        resolver=resolver,
        **fetch,
    )


async def manual_instance(
    engine: WorkflowEngine,
    process: ProcessInstance,
    raw_url: object,
    *,
    resolver: Resolver | None = None,
    **fetch: Any,
) -> dict[str, Any]:
    """The visitor pastes their instance URL: the same control proof against their token."""
    digest = (process.properties or {}).get(HASH_KEY)
    if not isinstance(digest, str):
        raise CallbackError("Make your one-time token first.", 410)
    return await complete_with_instance(
        engine,
        process,
        digest,
        normalize_instance_url(raw_url),
        via="manual",
        resolver=resolver,
        **fetch,
    )
