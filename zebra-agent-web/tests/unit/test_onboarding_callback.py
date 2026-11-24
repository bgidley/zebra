"""The onboarding callback (#278 S4): one-time token, control proof, SSRF guards."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx
import pytest
from django.test import Client
from zebra_agent_web.api import onboarding as ob
from zebra_agent_web.api import onboarding_callback as cb

# ---------------------------------------------------------------------------
# SSRF guards (no database)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://zebra.example.com",  # not https
        "https://zebra.example.com:8443",  # not 443
        "https://user:pw@zebra.example.com",  # credentials
        "https://zebra.example.com/admin",  # a path
        "https://zebra.example.com/?x=1",  # a query
        "https://10.0.0.5",  # private
        "https://127.0.0.1",  # loopback
        "https://[::1]",  # loopback v6
        "https://169.254.169.254",  # link-local (cloud metadata)
        "https://100.64.0.1",  # CGNAT
        "https://[fd00::1]",  # unique local v6
        "https://[::ffff:127.0.0.1]",  # IPv4-mapped loopback
        "https://0.0.0.0",  # unspecified
        "https://224.0.0.1",  # multicast
        "https://2130706433",  # decimal 127.0.0.1
        "https://localhost",  # no public TLD
        "file:///etc/passwd",
        "",
        None,
    ],
)
def test_refused_instance_urls(url):
    with pytest.raises(cb.CallbackError) as e:
        cb.normalize_instance_url(url)
    assert e.value.status == 400


@pytest.mark.parametrize(
    "url, origin",
    [
        ("https://Zebra.Example.com", "https://zebra.example.com"),
        ("https://zebra.example.com/", "https://zebra.example.com"),
        ("https://zebra.example.com:443", "https://zebra.example.com"),
        ("https://8.8.8.8", "https://8.8.8.8"),
        ("https://[2001:4860:4860::8888]", "https://[2001:4860:4860::8888]"),
    ],
)
def test_accepted_instance_urls(url, origin):
    assert cb.normalize_instance_url(url) == origin


def _page_hosts(page: str) -> set[str]:
    """Hostnames of every https URL shown on *page* (parsed, not substring-matched)."""
    return {urlsplit(url).hostname for url in re.findall(r"https://[^\s\"'<>]+", page)}


def _resolver(*answers):
    async def resolve(_host):
        return list(answers)

    return resolve


@pytest.mark.parametrize(
    "answers",
    [
        ("10.1.2.3",),
        ("8.8.8.8", "192.168.1.1"),  # one private answer refuses the host
        ("100.100.1.1",),
        ("fe80::1",),
        ("fec0::1",),  # deprecated site-local
        ("::ffff:10.0.0.1",),
        ("2002:a00:1::1",),  # 6to4 around 10.0.0.1
        (),
    ],
)
async def test_hosts_with_any_non_public_answer_are_refused(answers):
    with pytest.raises(cb.CallbackError) as e:
        await cb.resolve_public("zebra.example.com", _resolver(*answers))
    assert e.value.status == 422


async def test_a_failing_lookup_is_refused():
    async def broken(_host):
        raise OSError("no such host")

    with pytest.raises(cb.CallbackError):
        await cb.resolve_public("zebra.example.com", broken)


class _Recorder:
    """An httpx transport that records requests and answers with *handler*."""

    def __init__(self, handler):
        self.requests: list[httpx.Request] = []
        self._handler = handler

    def transport(self) -> httpx.MockTransport:
        async def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return await self._handler(request)

        return httpx.MockTransport(handle)


class _Stream(httpx.AsyncByteStream):
    """A response body that arrives over the wire in chunks, like a real one."""

    def __init__(self, data: bytes, chunk: int = 1024):
        self._data, self._chunk = data, chunk

    async def __aiter__(self):
        for i in range(0, len(self._data), self._chunk):
            yield self._data[i : i + self._chunk]


def _response(status: int, data: bytes = b"", **kwargs) -> httpx.Response:
    return httpx.Response(status, stream=_Stream(data), **kwargs)


async def _ok(_request):
    return _response(200, b"a" * 64)


async def test_fetch_is_pinned_to_the_checked_ip_with_sni_and_host():
    rec = _Recorder(_ok)
    body = await cb.fetch_challenge(
        "https://zebra.example.com", resolver=_resolver("8.8.4.4"), transport=rec.transport()
    )
    assert body == "a" * 64
    [request] = rec.requests
    assert str(request.url) == "https://8.8.4.4/.well-known/zebra-onboarding"
    assert request.headers["host"] == "zebra.example.com"
    assert request.extensions["sni_hostname"] == "zebra.example.com"


async def test_dns_rebinding_cannot_move_the_target():
    """The second lookup an HTTP client would do never happens: the IP is pinned."""
    answers = iter([["8.8.4.4"], ["127.0.0.1"]])

    async def rebinding(_host):
        return next(answers)

    rec = _Recorder(_ok)
    await cb.fetch_challenge(
        "https://zebra.example.com", resolver=rebinding, transport=rec.transport()
    )
    assert [r.url.host for r in rec.requests] == ["8.8.4.4"]


@pytest.mark.parametrize(
    "url, answers",
    [
        ("https://zebra.example.com", ("10.0.0.7",)),
        ("https://zebra.example.com", ("8.8.8.8", "127.0.0.1")),
        ("https://169.254.169.254", ()),
        ("http://zebra.example.com", ("8.8.8.8",)),
    ],
)
async def test_private_or_non_https_targets_are_never_fetched(url, answers):
    rec = _Recorder(_ok)
    with pytest.raises(cb.CallbackError):
        await cb.fetch_challenge(url, resolver=_resolver(*answers), transport=rec.transport())
    assert rec.requests == []


async def test_redirects_are_not_followed():
    async def redirect(_request):
        return _response(302, headers={"Location": "https://169.254.169.254/latest/"})

    rec = _Recorder(redirect)
    with pytest.raises(cb.CallbackError) as e:
        await cb.fetch_challenge(
            "https://zebra.example.com", resolver=_resolver("8.8.8.8"), transport=rec.transport()
        )
    assert e.value.status == 422
    assert len(rec.requests) == 1


async def test_oversized_bodies_are_refused():
    async def big(_request):
        return _response(200, b"a" * (cb.FETCH_MAX_BYTES + 1))

    with pytest.raises(cb.CallbackError) as e:
        await cb.fetch_challenge(
            "https://zebra.example.com",
            resolver=_resolver("8.8.8.8"),
            transport=_Recorder(big).transport(),
        )
    assert "too large" in e.value.message


async def test_slow_responses_time_out():
    async def slow(_request):
        await asyncio.sleep(5)
        return _response(200, b"a" * 64)

    started = asyncio.get_running_loop().time()
    with pytest.raises(cb.CallbackError) as e:
        await cb.fetch_challenge(
            "https://zebra.example.com",
            resolver=_resolver("8.8.8.8"),
            transport=_Recorder(slow).transport(),
            timeout=0.2,
        )
    assert "in time" in e.value.message
    assert asyncio.get_running_loop().time() - started < 2


async def test_slow_dns_counts_towards_the_timeout():
    async def slow_dns(_host):
        await asyncio.sleep(5)
        return ["8.8.8.8"]

    with pytest.raises(cb.CallbackError):
        await cb.fetch_challenge(
            "https://zebra.example.com",
            resolver=slow_dns,
            transport=_Recorder(_ok).transport(),
            timeout=0.2,
        )


def test_the_default_limits_are_the_designs():
    assert cb.FETCH_TIMEOUT_SECONDS == 5.0
    assert cb.FETCH_MAX_BYTES == 4096
    assert cb.TOKEN_TTL == timedelta(hours=1)


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b'{"token": "short"}', b'{"token": 1}'],
)
def test_bad_bodies_are_400(body):
    with pytest.raises(cb.CallbackError) as e:
        cb.parse_request(body)
    assert e.value.status == 400


def test_oversized_request_is_413():
    with pytest.raises(cb.CallbackError) as e:
        cb.parse_request(b"{" + b" " * 5000 + b"}")
    assert e.value.status == 413


# ---------------------------------------------------------------------------
# End to end through the views (a fake instance answers the control proof)
# ---------------------------------------------------------------------------


def _task_id(client: Client) -> str:
    page = client.get("/onboarding/").content.decode()
    return page.split('name="task_id" value="', 1)[1].split('"', 1)[0]


def _submit(client: Client, route: str, **fields):
    return client.post(
        "/onboarding/step/", {"task_id": _task_id(client), "next_route": route, **fields}
    )


def _make_token(client: Client) -> str:
    response = client.post("/onboarding/token/")
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    page = response.content.decode()
    return page.split('aria-label="One-time token"', 1)[0].rsplit('value="', 1)[1].split('"')[0]


def _to_provision(client: Client) -> None:
    assert client.post("/onboarding/start/").status_code == 302
    _submit(client, "done", home_region="uk-london-1", account_created="on", budget_ack="on")
    _submit(client, "done", name="mine")


def _to_await(client: Client) -> str:
    _to_provision(client)
    token = _make_token(client)
    assert _submit(client, "done", applied="on").status_code == 302
    return token


@pytest.fixture
def instance(monkeypatch):
    """A fake instance: ``serves[url]`` is what its well-known URL returns; records fetches."""
    state = {"serves": {}, "fetched": []}

    async def fetch(url, **_kwargs):
        state["fetched"].append(url)
        if url not in state["serves"]:
            raise cb.CallbackError("Could not reach the instance over https.", 422)
        return state["serves"][url]

    monkeypatch.setattr(cb, "fetch_challenge", fetch)
    return state


def _call(token: str, url: str = "https://zebra.example.com", **extra):
    body = {"token": token, "instance_url": url, "version": "1.4.0", **extra}
    return Client(REMOTE_ADDR="198.51.100.20").post(
        "/onboarding/callback/", json.dumps(body), content_type="application/json"
    )


def _props():
    from zebra_agent_web.api.models import ProcessInstanceModel, TaskInstanceModel

    [model] = ProcessInstanceModel.objects.all()
    tasks = sorted(
        (t.task_definition_id, t.state)
        for t in TaskInstanceModel.objects.filter(process_id=model.id)
    )
    return json.loads(model.properties), tasks


pytestmark_db = pytest.mark.django_db(transaction=True)


@pytestmark_db
def test_a_token_completes_exactly_one_session(onboarding_env, instance):
    client = Client()
    token = _to_await(client)
    instance["serves"]["https://zebra.example.com"] = cb.token_hash(token) + "\n"
    fingerprint = "ab" * 32

    response = _call(token, commons_fingerprint=fingerprint)
    assert response.status_code == 200, response.content
    assert response.json() == {"status": "ok"}

    props, _tasks = _props()
    assert props[cb.USED_KEY] is True
    output = props["__task_output_await_instance"]
    assert output["instance_url"] == "https://zebra.example.com"
    assert output["version"] == "1.4.0" and output["commons_fingerprint"] == fingerprint
    assert output["via"] == "callback"
    page = client.get("/onboarding/").content.decode()
    assert "Check it works" in page and "zebra.example.com" in _page_hosts(page)

    # O1: the token itself is nowhere in the session
    assert token not in json.dumps(props)
    assert props[cb.HASH_KEY] == cb.token_hash(token)

    # A replay gets 410 and changes nothing
    before = _props()
    replay = _call(token)
    assert replay.status_code == 410
    assert _props() == before


@pytestmark_db
def test_unknown_and_rotated_tokens_get_410(onboarding_env, instance):
    client = Client()
    old = _to_await(client)
    new = _make_token(client)  # rotates: the old one stops working
    instance["serves"]["https://zebra.example.com"] = cb.token_hash(old)
    before = _props()
    assert _call(old).status_code == 410
    assert _call("A" * 43).status_code == 410
    assert _props() == before
    assert instance["fetched"] == []  # nothing is fetched for a dead token
    instance["serves"]["https://zebra.example.com"] = cb.token_hash(new)
    assert _call(new).status_code == 200


@pytestmark_db
def test_an_expired_token_gets_410_and_changes_nothing(onboarding_env, instance):
    from asgiref.sync import async_to_sync

    client = Client()
    token = _to_await(client)
    instance["serves"]["https://zebra.example.com"] = cb.token_hash(token)
    engine, _library = onboarding_env
    props, _ = _props()
    from zebra_agent_web.api.models import ProcessInstanceModel

    pid = ProcessInstanceModel.objects.get().id
    past = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    async_to_sync(ob._update_properties)(engine.store, pid, {cb.EXPIRES_KEY: past})
    before = _props()
    assert _call(token).status_code == 410
    assert _props() == before
    assert "expired" in client.get("/onboarding/").content.decode()


@pytestmark_db
def test_a_failed_proof_leaves_the_token_unused(onboarding_env, instance):
    client = Client()
    token = _to_await(client)
    instance["serves"]["https://zebra.example.com"] = "0" * 64  # not our hash
    response = _call(token)
    assert response.status_code == 422
    props, tasks = _props()
    assert props[cb.USED_KEY] is False
    assert ("await_instance", "ready") in [(t, s.lower()) for t, s in tasks]
    # The real instance then proves it: still works
    instance["serves"]["https://zebra.example.com"] = cb.token_hash(token)
    assert _call(token).status_code == 200


@pytestmark_db
def test_a_session_not_yet_waiting_gets_409(onboarding_env, instance):
    client = Client()
    _to_provision(client)
    token = _make_token(client)
    instance["serves"]["https://zebra.example.com"] = cb.token_hash(token)
    assert _call(token).status_code == 409
    props, _ = _props()
    assert props[cb.USED_KEY] is False
    assert instance["fetched"] == []


@pytestmark_db
def test_lookup_survives_a_cache_miss(onboarding_env, instance):
    from django.core.cache import cache

    client = Client()
    token = _to_await(client)
    instance["serves"]["https://zebra.example.com"] = cb.token_hash(token)
    cache.clear()  # e.g. a restart: the RUNNING-session scan finds it
    assert _call(token).status_code == 200


@pytestmark_db
def test_callback_bad_input_rate_limit_and_switch(onboarding_env, instance, settings):
    from zebra_agent_web.api.models import SystemStateModel

    bad = Client(REMOTE_ADDR="198.51.100.30")
    assert (
        bad.post("/onboarding/callback/", "nope", content_type="application/json").status_code
        == 400
    )
    assert bad.get("/onboarding/callback/").status_code == 405
    codes = [
        Client(REMOTE_ADDR="198.51.100.31")
        .post("/onboarding/callback/", "{}", content_type="application/json")
        .status_code
        for _ in range(cb.CALLBACKS_PER_IP_MINUTE + 1)
    ]
    assert codes[-1] == 429 and set(codes[:-1]) == {400}
    SystemStateModel.objects.filter(pk=1).update(onboarding_enabled=False)
    assert _call("A" * 43).status_code == 404


@pytestmark_db
def test_the_callback_needs_no_csrf_token(onboarding_env, instance):
    client = Client(enforce_csrf_checks=True, REMOTE_ADDR="198.51.100.40")
    response = client.post(
        "/onboarding/callback/",
        json.dumps({"token": "A" * 43, "instance_url": "https://zebra.example.com"}),
        content_type="application/json",
    )
    assert response.status_code == 410


@pytestmark_db
def test_manual_paste_uses_the_same_proof(onboarding_env, instance):
    client = Client()
    token = _to_await(client)
    response = client.post("/onboarding/instance/", {"instance_url": "https://zebra.example.com"})
    assert response.status_code == 422  # nothing answers yet
    response = client.post("/onboarding/instance/", {"instance_url": "http://10.0.0.1"})
    assert response.status_code == 400 and "https" in response.content.decode()
    instance["serves"]["https://zebra.example.com"] = cb.token_hash(token)
    assert (
        client.post(
            "/onboarding/instance/", {"instance_url": "https://zebra.example.com"}
        ).status_code
        == 302
    )
    props, _ = _props()
    assert props["__task_output_await_instance"]["via"] == "manual"
    assert props[cb.USED_KEY] is True


@pytestmark_db
def test_the_visitor_can_report_a_problem_while_waiting(onboarding_env, instance):
    client = Client()
    _to_await(client)
    page = client.get("/onboarding/").content.decode()
    waiting_task = page.split('name="task_id" value="', 1)[1].split('"', 1)[0]
    response = client.post(
        "/onboarding/step/",
        {"task_id": waiting_task, "next_route": "done", "problem": "x"},
    )
    assert response.status_code == 400  # only "problem" from the waiting screen
    response = client.post(
        "/onboarding/step/",
        {"task_id": waiting_task, "next_route": "problem", "problem": "The Apply job failed"},
    )
    assert response.status_code == 302
    page = client.get("/onboarding/").content.decode()
    assert "The Apply job failed" in page and "Try this step again" in page


@pytestmark_db
def test_provision_needs_a_token_before_it_moves_on(onboarding_env):
    client = Client()
    _to_provision(client)
    response = _submit(client, "done", applied="on")
    assert response.status_code == 400
    assert "Make your one-time token first" in response.content.decode()


@pytestmark_db
def test_token_is_only_made_on_the_provision_step(onboarding_env):
    client = Client()
    client.post("/onboarding/start/")
    assert client.post("/onboarding/token/").status_code == 409
    props, _ = _props()
    assert cb.HASH_KEY not in props


@pytestmark_db
def test_the_token_never_reaches_a_log(onboarding_env, instance, caplog):
    caplog.set_level(logging.DEBUG)
    client = Client()
    token = _to_await(client)
    instance["serves"]["https://zebra.example.com"] = cb.token_hash(token)
    _call(token)
    _call(token)
    assert token not in caplog.text


async def test_two_concurrent_callbacks_complete_once(monkeypatch):
    """Both pass the proof; the compare-and-set lets exactly one claim the token.

    An in-memory store keeps SQLite's single-writer locking out of the race; its process lock
    is re-entrant per owner like the Django store's, so this also guards the per-claim owner.
    """
    from zebra.core.engine import WorkflowEngine
    from zebra.core.models import TaskResult
    from zebra.definitions.loader import load_definition
    from zebra.storage.memory import InMemoryStore
    from zebra.tasks.registry import ActionRegistry
    from zebra_agent.library import BUILTIN_WORKFLOWS_DIR

    registry = ActionRegistry()
    registry.register_defaults()
    engine = WorkflowEngine(InMemoryStore(), registry)
    definition = load_definition(BUILTIN_WORKFLOWS_DIR / "onboarding.yaml")
    process = await engine.create_process(
        definition, properties={ob.MARKER_KEY: True, ob.NONCE_KEY: "0" * 64}
    )
    process = await engine.start_process(process.id)
    signup = {"home_region": "uk-london-1", "account_created": True, "budget_ack": True}
    for route, output in [("done", signup), ("done", {"name": "mine"})]:
        state = await ob.wizard_state(engine.store, process)
        await engine.complete_task(
            state.task_id, TaskResult(success=True, output=output, next_route=route)
        )
    token = await cb.issue_token(engine.store, process.id)
    state = await ob.wizard_state(engine.store, process)
    await engine.complete_task(
        state.task_id, TaskResult(success=True, output={"applied": True}, next_route="done")
    )

    async def proof(*_args, **_kwargs):
        await asyncio.sleep(0.05)  # both pass the proof before either claims

    monkeypatch.setattr(cb, "verify_control", proof)
    # Reads take time and return copies, as a database does: without the lock both would see
    # the token unused
    real_load = engine.store.load_process

    async def slow_load(process_id):
        loaded = await real_load(process_id)
        await asyncio.sleep(0.02)
        return loaded.model_copy(deep=True) if loaded else loaded

    monkeypatch.setattr(engine.store, "load_process", slow_load)
    body = json.dumps({"token": token, "instance_url": "https://zebra.example.com"}).encode()
    results = await asyncio.gather(
        cb.handle_callback(engine, body), cb.handle_callback(engine, body), return_exceptions=True
    )
    ok = [r for r in results if isinstance(r, dict)]
    refused = [r for r in results if isinstance(r, cb.CallbackError)]
    assert len(ok) == 1 and len(refused) == 1, results
    assert refused[0].status in (409, 410)
    process = await engine.store.load_process(process.id)
    assert process.properties[cb.USED_KEY] is True
