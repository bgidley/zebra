"""Tests for NotifyWebhookAction."""

import json
from unittest.mock import patch

import httpx
import pytest
from zebra.core.models import TaskInstance, TaskState

from zebra_tasks.notifications.webhook import NotifyWebhookAction

MODULE = "zebra_tasks.notifications.webhook"
_RealAsyncClient = httpx.AsyncClient


def make_task(properties: dict) -> TaskInstance:
    return TaskInstance(
        id="task-1",
        process_id="proc-1",
        task_definition_id="notify",
        state=TaskState.RUNNING,
        foe_id="foe-1",
        properties=properties,
    )


class Recorder:
    """Records requests and replies with a fixed response."""

    def __init__(self, status_code: int = 200, text: str = "ok", error: Exception | None = None):
        self.requests: list[httpx.Request] = []
        self.status_code = status_code
        self.text = text
        self.error = error

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error:
            raise self.error
        return httpx.Response(self.status_code, text=self.text)

    def client_factory(self, **kwargs):
        return _RealAsyncClient(transport=httpx.MockTransport(self.handler), **kwargs)


@pytest.fixture
def action():
    return NotifyWebhookAction()


@pytest.fixture(autouse=True)
def no_default_url(monkeypatch):
    monkeypatch.delenv("ZEBRA_NOTIFY_WEBHOOK_URL", raising=False)


async def run_with(action, task, context, recorder):
    with patch(f"{MODULE}.httpx.AsyncClient", recorder.client_factory):
        return await action.run(task, context)


async def test_posts_json_payload_with_resolved_templates(action, mock_context):
    mock_context.process.properties["goal"] = "write digest"
    recorder = Recorder()
    task = make_task(
        {
            "url": "https://hooks.example.com/T123/secret",
            "payload": {"text": "Done: {{goal}}", "blocks": [{"t": "{{goal}}"}], "n": 3},
            "headers": {"X-Token": "abc"},
        }
    )

    result = await run_with(action, task, mock_context, recorder)

    assert result.success
    assert result.output == {"status_code": 200, "host": "hooks.example.com"}
    request = recorder.requests[0]
    assert request.method == "POST"
    assert request.headers["X-Token"] == "abc"
    assert json.loads(request.content) == {
        "text": "Done: write digest",
        "blocks": [{"t": "write digest"}],
        "n": 3,
    }


async def test_raw_body_and_put(action, mock_context):
    recorder = Recorder(status_code=204, text="")
    task = make_task({"url": "https://ntfy.example.com/zebra", "body": "hello", "method": "put"})

    result = await run_with(action, task, mock_context, recorder)

    assert result.success
    assert recorder.requests[0].method == "PUT"
    assert recorder.requests[0].content == b"hello"


async def test_defaults_url_from_env(action, mock_context, monkeypatch):
    monkeypatch.setenv("ZEBRA_NOTIFY_WEBHOOK_URL", "https://env.example.com/hook?token=x")
    recorder = Recorder()

    result = await run_with(action, make_task({"payload": {"a": 1}}), mock_context, recorder)

    assert result.success
    assert str(recorder.requests[0].url) == "https://env.example.com/hook?token=x"
    assert "token" not in json.dumps(result.output)


async def test_non_2xx_fails(action, mock_context):
    recorder = Recorder(status_code=500, text="boom")
    task = make_task({"url": "https://hooks.example.com/secret-path", "payload": {"a": 1}})

    result = await run_with(action, task, mock_context, recorder)

    assert not result.success
    assert "500" in result.error
    assert "secret-path" not in result.error


async def test_network_error_fails(action, mock_context):
    recorder = Recorder(error=httpx.ConnectError("nope"))
    task = make_task({"url": "https://hooks.example.com/x", "payload": {"a": 1}})

    result = await run_with(action, task, mock_context, recorder)

    assert not result.success
    assert "hooks.example.com" in result.error


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "ftp://example.com/x", "not a url", "https:///nohost"]
)
async def test_rejects_bad_urls_without_request(action, mock_context, url):
    recorder = Recorder()
    result = await run_with(action, make_task({"url": url, "payload": {}}), mock_context, recorder)

    assert not result.success
    assert recorder.requests == []


async def test_fails_without_url(action, mock_context):
    recorder = Recorder()
    result = await run_with(action, make_task({"payload": {}}), mock_context, recorder)

    assert not result.success
    assert "ZEBRA_NOTIFY_WEBHOOK_URL" in result.error


async def test_fails_without_payload_or_body(action, mock_context):
    recorder = Recorder()
    result = await run_with(
        action, make_task({"url": "https://hooks.example.com/x"}), mock_context, recorder
    )

    assert not result.success
    assert recorder.requests == []


async def test_rejects_unsupported_method(action, mock_context):
    recorder = Recorder()
    task = make_task({"url": "https://hooks.example.com/x", "payload": {}, "method": "DELETE"})

    result = await run_with(action, task, mock_context, recorder)

    assert not result.success
    assert recorder.requests == []


def test_metadata_declares_irreversible():
    metadata = NotifyWebhookAction.get_metadata()
    assert metadata.reversibility_hint == "always_irreversible"
    assert metadata.description
