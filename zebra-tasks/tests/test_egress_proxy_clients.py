"""Every outbound client honours HTTPS_PROXY / NO_PROXY (#337).

Behavioural tests send each client's real code path at a recording proxy and assert the proxy
saw the CONNECT. A source scan keeps the audit true: no HTTP client may switch the proxy off
(``trust_env=False``) or pin its own transport, and no module may open sockets or use a client
library that ignores the proxy, except the ones listed here with the reason.
"""

import re
from pathlib import Path

import pytest
from zebra.core.models import TaskInstance, TaskState

from zebra_tasks.http.actions import HttpGetAction
from zebra_tasks.llm.base import Message
from zebra_tasks.llm.openrouter import OpenRouterLLM
from zebra_tasks.notifications.webhook import NotifyWebhookAction
from zebra_tasks.web.kagi_extract import KagiExtractAction
from zebra_tasks.web.kagi_news import KagiNewsFetchAction, KagiNewsReadAction
from zebra_tasks.web.kagi_search import KagiSearchAction

ROOT = Path(__file__).parents[2]


def _task(properties: dict) -> TaskInstance:
    return TaskInstance(
        id="t1",
        process_id="p1",
        task_definition_id="call",
        state=TaskState.RUNNING,
        foe_id="f1",
        properties=properties,
    )


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", "k-test")
    monkeypatch.delenv("ZEBRA_HTTP_ALLOWED_PRIVATE_HOSTS", raising=False)


async def test_kagi_search_goes_through_the_proxy(recording_proxy, mock_context):
    result = await KagiSearchAction().run(_task({"query": "zebras"}), mock_context)

    assert not result.success
    assert recording_proxy.connects == ["kagi.com:443"]


async def test_kagi_extract_goes_through_the_proxy(recording_proxy, mock_context):
    result = await KagiExtractAction().run(_task({"url": "https://example.org"}), mock_context)

    assert not result.success
    assert recording_proxy.connects == ["kagi.com:443"]


async def test_kagi_news_fetch_goes_through_the_proxy(recording_proxy, mock_context):
    result = await KagiNewsFetchAction().run(_task({}), mock_context)

    assert not result.success
    assert recording_proxy.connects == ["news.kagi.com:443"]


async def test_kagi_news_read_extract_goes_through_the_proxy(recording_proxy):
    extracted = await KagiNewsReadAction._extract(["https://example.org/a"], 1000)

    assert extracted == {}
    assert recording_proxy.connects == ["kagi.com:443"]


async def test_webhook_goes_through_the_proxy(recording_proxy, mock_context):
    props = {"url": "https://hooks.example.com/x", "payload": {"a": 1}}

    result = await NotifyWebhookAction().run(_task(props), mock_context)

    assert not result.success
    assert recording_proxy.connects == ["hooks.example.com:443"]


async def test_plain_http_webhook_is_sent_to_the_proxy_in_absolute_form(
    recording_proxy, mock_context
):
    recording_proxy.http_reply = (200, b"{}")
    props = {"url": "http://hooks.example.com/x", "payload": {"a": 1}}

    result = await NotifyWebhookAction().run(_task(props), mock_context)

    assert result.success
    assert [(r.method, r.target) for r in recording_proxy.requests] == [
        ("POST", "http://hooks.example.com/x")
    ]


async def test_http_get_goes_through_the_proxy_without_local_dns(recording_proxy, mock_context):
    # check_url must not resolve the name here: the sandbox has no public DNS
    result = await HttpGetAction().run(
        _task({"url": "https://no-such-host.invalid/data"}), mock_context
    )

    assert not result.success
    assert recording_proxy.connects == ["no-such-host.invalid:443"]


async def test_http_get_still_refuses_a_private_ip_literal_behind_the_proxy(
    recording_proxy, mock_context
):
    result = await HttpGetAction().run(_task({"url": "https://10.1.2.3/x"}), mock_context)

    assert not result.success
    assert recording_proxy.requests == []


async def test_no_proxy_host_bypasses_the_proxy(recording_proxy, mock_context, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "hooks.example.com")
    monkeypatch.setenv("no_proxy", "hooks.example.com")
    props = {"url": "https://hooks.example.com/x", "payload": {"a": 1}}

    result = await NotifyWebhookAction().run(_task(props), mock_context)

    assert not result.success  # no route to the made-up host
    assert recording_proxy.requests == []


async def test_openrouter_client_goes_through_the_proxy(recording_proxy, monkeypatch):
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.test/api/v1")
    monkeypatch.setattr("zebra_tasks.llm.openrouter.LLM_MAX_RETRIES", 0)
    llm = OpenRouterLLM(api_key="k-test")

    with pytest.raises(Exception, match="onnection|403"):
        await llm.complete([Message.user("hi")])

    assert recording_proxy.connects == ["openrouter.test:443"]


# --- source audit -------------------------------------------------------------------------

PACKAGES = ["zebra-py/zebra", "zebra-tasks/zebra_tasks", "zebra-agent/zebra_agent"]
PACKAGES += ["zebra-agent-web/zebra_agent_web"]

#: path (under the repo) -> why it may do what the scan forbids
EXEMPT = {
    "zebra-agent-web/zebra_agent_web/api/onboarding_callback.py": (
        "SSRF-pinned fetch of an anonymous visitor's instance URL; deliberately direct. "
        "Onboarding is off in the work sandbox."
    ),
    "zebra-tasks/zebra_tasks/notifications/smtp_email.py": (
        "SMTP cannot use an HTTP proxy; unsupported in the work sandbox (runbook)"
    ),
    "zebra-agent/zebra_agent/commons/nostr.py": "relay transport; proxy support is #338",
}

FORBIDDEN_CLIENT_ARGS = re.compile(r"trust_env\s*=\s*False|\bproxy\s*=|\bproxies\s*=|\bmounts\s*=")
UNAUDITED_CLIENTS = re.compile(
    r"^\s*(?:import|from)\s+(?:aiohttp|requests|websockets|websocket|smtplib|ftplib|telnetlib|"
    r"socks|urllib3)\b|urllib\.request\.urlopen|\bcreate_connection\(|asyncio\.open_connection\(",
    re.MULTILINE,
)


def _sources():
    for package in PACKAGES:
        for path in sorted((ROOT / package).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if "/tests/" not in rel and rel not in EXEMPT:
                yield rel, path.read_text()


def test_no_http_client_switches_the_proxy_off():
    offenders = [rel for rel, text in _sources() if FORBIDDEN_CLIENT_ARGS.search(text)]

    assert offenders == [], "set HTTPS_PROXY must reach every client; exempt with a reason"


def test_no_unaudited_network_client_library():
    offenders = [rel for rel, text in _sources() if UNAUDITED_CLIENTS.search(text)]

    assert offenders == [], "audit it for HTTPS_PROXY (#337) and fix or list it in EXEMPT"


def test_exemptions_still_exist():
    for rel in EXEMPT:
        assert (ROOT / rel).exists(), f"{rel} is gone; drop it from EXEMPT"
