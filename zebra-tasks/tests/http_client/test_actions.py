"""Tests for the http_get / http_request task actions (F62)."""

import json
from collections.abc import Callable
from unittest.mock import patch

import httpx
import pytest
from zebra.core.models import TaskInstance, TaskState

from zebra_tasks.http.actions import HttpGetAction, HttpRequestAction

_RealAsyncClient = httpx.AsyncClient

PUBLIC = {
    "api.example.com": "93.184.216.34",
    "api.github.com": "140.82.112.6",
    "other.example": "93.184.216.35",
    "sneaky.example": "93.184.216.36",
    "rebind.example": "127.0.0.1",
}


OUTPUT_KEYS = {
    "status_code",
    "host",
    "url",
    "content_type",
    "headers",
    "body",
    "json",
    "truncated",
}


def make_task(properties: dict) -> TaskInstance:
    return TaskInstance(
        id="task-1",
        process_id="proc-1",
        task_definition_id="call",
        state=TaskState.RUNNING,
        foe_id="foe-1",
        properties=properties,
    )


class Server:
    """Fake HTTP server: records requests and answers with a handler."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]):
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)

    def client_factory(self, **kwargs):
        return _RealAsyncClient(transport=httpx.MockTransport(self._handle), **kwargs)


async def fake_resolve(host: str, port: int) -> list[str]:
    if host not in PUBLIC:
        raise OSError("unknown host")
    return [PUBLIC[host]]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("ZEBRA_HTTP_ALLOWED_PRIVATE_HOSTS", raising=False)
    monkeypatch.setenv(
        "ZEBRA_HTTP_CRED_GITHUB",
        json.dumps({"host": "api.github.com", "type": "bearer", "token": "t0k-secret"}),
    )


async def run(action, properties, context, server):
    with (
        patch("zebra_tasks.http.guard._resolve", fake_resolve),
        patch("zebra_tasks.http.actions.httpx.AsyncClient", server.client_factory),
    ):
        return await action.run(make_task(properties), context)


def json_reply(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, "items": [1, 2]})


async def test_get_returns_parsed_json_and_sends_query(mock_context):
    mock_context.process.properties["topic"] = "zebras"
    server = Server(json_reply)

    result = await run(
        HttpGetAction(),
        {"url": "https://api.example.com/search?x=1", "query": {"q": "{{topic}}"}},
        mock_context,
        server,
    )

    assert result.success
    out = result.output
    assert set(out) == OUTPUT_KEYS
    assert out["status_code"] == 200
    assert out["json"] == {"ok": True, "items": [1, 2]}
    assert json.loads(out["body"]) == out["json"]
    assert out["host"] == "api.example.com"
    assert out["url"] == "https://api.example.com/search"
    assert out["truncated"] is False
    assert server.requests[0].method == "GET"
    assert server.requests[0].url.params["q"] == "zebras"
    json.dumps(out)  # properties must be JSON-serialisable


async def test_get_drops_set_cookie_and_keeps_text(mock_context):
    server = Server(
        lambda r: httpx.Response(
            200, text="hello", headers={"content-type": "text/plain", "set-cookie": "s=1"}
        )
    )

    result = await run(HttpGetAction(), {"url": "https://api.example.com/"}, mock_context, server)

    assert result.output["body"] == "hello"
    assert result.output["json"] is None
    assert "set-cookie" not in {k.lower() for k in result.output["headers"]}


@pytest.mark.parametrize("method", ["POST", "DELETE"])
async def test_get_refuses_write_methods(mock_context, method):
    server = Server(json_reply)
    result = await run(
        HttpGetAction(), {"url": "https://api.example.com/", "method": method}, mock_context, server
    )
    assert not result.success
    assert "GET, HEAD" in result.error
    assert server.requests == []


async def test_request_posts_resolved_json(mock_context):
    mock_context.process.properties["goal"] = "fix the gate"
    server = Server(lambda r: httpx.Response(201, json={"id": 7}))

    result = await run(
        HttpRequestAction(),
        {
            "method": "post",
            "url": "https://api.example.com/issues",
            "json": {"title": "{{goal}}", "labels": ["{{goal}}"], "n": 3},
            "headers": {"X-Trace": "{{goal}}"},
        },
        mock_context,
        server,
    )

    assert result.success
    assert set(result.output) == OUTPUT_KEYS
    assert result.output["status_code"] == 201
    assert result.output["json"] == {"id": 7}
    request = server.requests[0]
    assert request.method == "POST"
    assert json.loads(request.content) == {
        "title": "fix the gate",
        "labels": ["fix the gate"],
        "n": 3,
    }
    assert request.headers["X-Trace"] == "fix the gate"


async def test_request_sends_raw_body(mock_context):
    server = Server(lambda r: httpx.Response(204))
    result = await run(
        HttpRequestAction(),
        {"method": "PUT", "url": "https://api.example.com/x", "body": "raw text"},
        mock_context,
        server,
    )
    assert result.success
    assert server.requests[0].content == b"raw text"


@pytest.mark.parametrize("props", [{}, {"method": "GET"}, {"method": "TRACE"}])
async def test_request_needs_a_write_method(mock_context, props):
    server = Server(json_reply)
    result = await run(
        HttpRequestAction(), {"url": "https://api.example.com/", **props}, mock_context, server
    )
    assert not result.success
    assert "POST, PUT, PATCH, DELETE" in result.error
    assert server.requests == []


async def test_request_refuses_json_and_body_together(mock_context):
    server = Server(json_reply)
    result = await run(
        HttpRequestAction(),
        {"method": "POST", "url": "https://api.example.com/", "json": {}, "body": "x"},
        mock_context,
        server,
    )
    assert not result.success
    assert server.requests == []


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:8000/admin/",
        "http://rebind.example/",
        "http://[::1]/",
    ],
)
async def test_internal_addresses_are_never_contacted(mock_context, url):
    server = Server(json_reply)
    result = await run(HttpGetAction(), {"url": url}, mock_context, server)
    assert not result.success
    assert "not a public address" in result.error
    assert server.requests == []


async def test_redirect_to_internal_address_is_not_followed(mock_context):
    server = Server(
        lambda r: httpx.Response(302, headers={"location": "http://127.0.0.1:8000/secrets"})
    )
    result = await run(HttpGetAction(), {"url": "https://api.example.com/go"}, mock_context, server)
    assert not result.success
    assert "not a public address" in result.error
    assert [str(r.url) for r in server.requests] == ["https://api.example.com/go"]


async def test_relative_redirect_is_followed(mock_context):
    def handler(request):
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(200, json={"path": request.url.path})

    server = Server(handler)
    result = await run(
        HttpGetAction(), {"url": "https://api.example.com/old"}, mock_context, server
    )
    assert result.success
    assert result.output["json"] == {"path": "/new"}
    assert result.output["url"] == "https://api.example.com/new"


async def test_303_after_post_becomes_get_without_body(mock_context):
    def handler(request):
        if request.method == "POST":
            return httpx.Response(303, headers={"location": "/result"})
        return httpx.Response(200, json={"method": request.method})

    server = Server(handler)
    result = await run(
        HttpRequestAction(),
        {"method": "POST", "url": "https://api.example.com/submit", "json": {"a": 1}},
        mock_context,
        server,
    )
    assert result.output["json"] == {"method": "GET"}
    assert server.requests[1].content == b""


async def test_redirect_loop_fails(mock_context):
    server = Server(lambda r: httpx.Response(302, headers={"location": "/again"}))
    result = await run(
        HttpGetAction(), {"url": "https://api.example.com/again"}, mock_context, server
    )
    assert not result.success
    assert "Too many redirects" in result.error
    assert len(server.requests) == 6


async def test_credential_is_sent_to_its_host(mock_context):
    server = Server(json_reply)
    result = await run(
        HttpGetAction(),
        {"url": "https://api.github.com/user", "credential": "github"},
        mock_context,
        server,
    )
    assert result.success
    assert server.requests[0].headers["Authorization"] == "Bearer t0k-secret"
    assert "t0k-secret" not in json.dumps(result.output)


async def test_credential_refused_for_another_host(mock_context):
    server = Server(json_reply)
    result = await run(
        HttpRequestAction(),
        {"method": "POST", "url": "https://sneaky.example/collect", "credential": "github"},
        mock_context,
        server,
    )
    assert not result.success
    assert "github" in result.error
    assert "t0k-secret" not in result.error
    assert server.requests == []


async def test_credential_dropped_on_cross_host_redirect(mock_context):
    def handler(request):
        if request.url.host == "api.github.com":
            return httpx.Response(302, headers={"location": "https://other.example/landing"})
        return httpx.Response(200, text="landed")

    server = Server(handler)
    result = await run(
        HttpGetAction(),
        {"url": "https://api.github.com/redirect", "credential": "github"},
        mock_context,
        server,
    )
    assert result.success
    assert server.requests[0].headers["Authorization"] == "Bearer t0k-secret"
    assert "Authorization" not in server.requests[1].headers


async def test_credential_never_logged(mock_context, caplog):
    caplog.set_level("DEBUG")
    server = Server(json_reply)
    await run(
        HttpGetAction(),
        {"url": "https://api.github.com/user", "credential": "github"},
        mock_context,
        server,
    )
    await run(
        HttpGetAction(),
        {"url": "https://sneaky.example/", "credential": "github"},
        mock_context,
        server,
    )
    assert caplog.records
    assert "t0k-secret" not in caplog.text


async def test_missing_credential_fails_before_sending(mock_context):
    server = Server(json_reply)
    result = await run(
        HttpGetAction(),
        {"url": "https://api.example.com/", "credential": "nope"},
        mock_context,
        server,
    )
    assert not result.success
    assert "ZEBRA_HTTP_CRED_NOPE" in result.error
    assert server.requests == []


async def test_body_over_max_bytes_is_cut(mock_context):
    big = json.dumps({"data": "x" * 5000})
    server = Server(
        lambda r: httpx.Response(200, text=big, headers={"content-type": "application/json"})
    )
    result = await run(
        HttpGetAction(), {"url": "https://api.example.com/", "max_bytes": 100}, mock_context, server
    )
    assert result.success
    assert result.output["truncated"] is True
    assert len(result.output["body"]) == 100
    assert result.output["json"] is None


async def test_max_bytes_and_timeout_are_capped(mock_context):
    seen = {}

    def factory(**kwargs):
        seen.update(kwargs)
        return _RealAsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, text="x" * 10)), **kwargs
        )

    server = Server(json_reply)
    server.client_factory = factory
    result = await run(
        HttpGetAction(),
        {"url": "https://api.example.com/", "timeout": 9999, "max_bytes": 10**9},
        mock_context,
        server,
    )
    assert result.success
    assert seen["timeout"] == 120.0
    assert seen["follow_redirects"] is False


async def test_max_bytes_is_capped_at_5mb(mock_context):
    server = Server(lambda r: httpx.Response(200, content=b"x" * 5_000_100))
    result = await run(
        HttpGetAction(),
        {"url": "https://api.example.com/", "max_bytes": 10**9},
        mock_context,
        server,
    )
    assert len(result.output["body"]) == 5_000_000
    assert result.output["truncated"] is True


async def test_error_status_fails_by_default(mock_context):
    server = Server(lambda r: httpx.Response(404, text="no such thing"))
    result = await run(HttpGetAction(), {"url": "https://api.example.com/x"}, mock_context, server)
    assert not result.success
    assert "404" in result.error
    assert "no such thing" in result.error


async def test_error_status_returned_when_not_failing(mock_context):
    server = Server(lambda r: httpx.Response(404, json={"error": "missing"}))
    result = await run(
        HttpGetAction(),
        {"url": "https://api.example.com/x", "fail_on_status": False},
        mock_context,
        server,
    )
    assert result.success
    assert result.output["status_code"] == 404
    assert result.output["json"] == {"error": "missing"}


async def test_network_error_names_host_only(mock_context):
    def boom(request):
        raise httpx.ConnectError("connection refused")

    server = Server(boom)
    result = await run(
        HttpGetAction(), {"url": "https://api.example.com/?key=s3cret"}, mock_context, server
    )
    assert not result.success
    assert "api.example.com" in result.error
    assert "s3cret" not in result.error


async def test_url_output_hides_userinfo_and_query(mock_context):
    server = Server(json_reply)
    result = await run(
        HttpGetAction(),
        {"url": "https://user:pw@api.example.com/a?token=s3cret#frag"},
        mock_context,
        server,
    )
    assert result.output["url"] == "https://api.example.com/a"


def test_reversibility_hints():
    assert HttpGetAction.reversibility_hint == "always_reversible"
    assert HttpRequestAction.reversibility_hint == "always_irreversible"
