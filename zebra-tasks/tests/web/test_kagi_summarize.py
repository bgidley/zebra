"""Tests for KagiSummarizeAction."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zebra.core.models import TaskInstance, TaskState

from zebra_tasks.web.kagi_summarize import KagiSummarizeAction

FAKE_KEY = "test-kagi-key"

MOCK_SUMMARIZE_RESPONSE = {
    "meta": {"id": "xyz", "node": "us-east"},
    "data": {
        "output": "This article discusses the key points about the topic in detail.",
        "tokens": 350,
    },
}


def make_task(properties: dict) -> TaskInstance:
    return TaskInstance(
        id="task-1",
        process_id="proc-1",
        task_definition_id="summarize",
        state=TaskState.RUNNING,
        foe_id="foe-1",
        properties=properties,
    )


@pytest.fixture
def action():
    return KagiSummarizeAction()


async def test_summarize_returns_summary(action, mock_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)

    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_SUMMARIZE_RESPONSE
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    task = make_task({"url": "https://example.com/article"})

    with patch("zebra_tasks.web.kagi_summarize.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(task, mock_context)

    assert result.success
    assert "key points" in result.output["summary"]
    assert result.output["url"] == "https://example.com/article"
    assert result.output["tokens"] == 350

    call_kwargs = mock_client.get.call_args
    assert call_kwargs.kwargs["params"]["url"] == "https://example.com/article"
    assert call_kwargs.kwargs["params"]["engine"] == "agnes"
    assert call_kwargs.kwargs["params"]["summary_type"] == "summary"


async def test_summarize_custom_options(action, mock_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)

    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_SUMMARIZE_RESPONSE
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    task = make_task(
        {
            "url": "https://example.com",
            "engine": "daphne",
            "summary_type": "takeaway",
            "output_key": "my_summary",
        }
    )

    with patch("zebra_tasks.web.kagi_summarize.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(task, mock_context)

    assert result.success
    call_kwargs = mock_client.get.call_args
    assert call_kwargs.kwargs["params"]["engine"] == "daphne"
    assert call_kwargs.kwargs["params"]["summary_type"] == "takeaway"
    assert mock_context.process.properties.get("my_summary") is not None


async def test_summarize_fails_without_url(action, mock_context):
    task = make_task({})
    result = await action.run(task, mock_context)
    assert not result.success
    assert "url" in result.error.lower()


async def test_summarize_fails_without_api_key(action, mock_context, monkeypatch):
    monkeypatch.delenv("KAGI_API_KEY", raising=False)
    task = make_task({"url": "https://example.com"})
    result = await action.run(task, mock_context)
    assert not result.success
    assert "KAGI_API_KEY" in result.error


async def test_summarize_handles_http_error(action, mock_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)

    import httpx

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    error_response = MagicMock()
    error_response.status_code = 403
    error_response.text = "forbidden"
    mock_client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError("forbidden", request=MagicMock(), response=error_response)
    )

    task = make_task({"url": "https://example.com"})

    with patch("zebra_tasks.web.kagi_summarize.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(task, mock_context)

    assert not result.success
    assert "403" in result.error


async def test_summarize_template_url(action, mock_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)

    mock_context.process.properties["target_url"] = "https://resolved.example.com"

    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_SUMMARIZE_RESPONSE
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    task = make_task({"url": "{{target_url}}"})

    with patch("zebra_tasks.web.kagi_summarize.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(task, mock_context)

    assert result.success
    assert result.output["url"] == "https://resolved.example.com"
