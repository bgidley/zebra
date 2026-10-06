"""Tests for KagiExtractAction."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from zebra.core.models import TaskInstance, TaskState

from zebra_tasks.web.kagi_extract import KagiExtractAction

FAKE_KEY = "test-kagi-key"

MOCK_EXTRACT_RESPONSE = {
    "meta": {"trace": "xyz", "node": "us-east", "ms": 900},
    "data": [
        {
            "url": "https://example.com/article",
            "markdown": "# Article\n\nThis article discusses the key points in detail.",
        }
    ],
}


def make_task(properties: dict) -> TaskInstance:
    return TaskInstance(
        id="task-1",
        process_id="proc-1",
        task_definition_id="extract",
        state=TaskState.RUNNING,
        foe_id="foe-1",
        properties=properties,
    )


def make_client(json_data: dict | None = None, side_effect: Exception | None = None) -> MagicMock:
    mock_response = MagicMock()
    mock_response.json.return_value = json_data
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response, side_effect=side_effect)
    return mock_client


@pytest.fixture
def action():
    return KagiExtractAction()


async def test_extract_returns_markdown(action, mock_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)
    mock_client = make_client(MOCK_EXTRACT_RESPONSE)

    task = make_task({"url": "https://example.com/article"})

    with patch("zebra_tasks.web.kagi_extract.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(task, mock_context)

    assert result.success
    assert "key points" in result.output["markdown"]
    assert result.output["url"] == "https://example.com/article"
    assert result.output["truncated"] is False
    assert "key points" in mock_context.process.properties["page_content"]

    call_kwargs = mock_client.post.call_args
    assert call_kwargs.args[0] == "https://kagi.com/api/v1/extract"
    assert call_kwargs.kwargs["json"] == {"pages": [{"url": "https://example.com/article"}]}
    assert call_kwargs.kwargs["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"


async def test_extract_truncates_and_custom_output_key(action, mock_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)
    mock_client = make_client(MOCK_EXTRACT_RESPONSE)

    task = make_task(
        {"url": "https://example.com/article", "max_chars": 9, "output_key": "my_page"}
    )

    with patch("zebra_tasks.web.kagi_extract.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(task, mock_context)

    assert result.success
    assert result.output["markdown"] == "# Article"
    assert result.output["truncated"] is True
    assert mock_context.process.properties["my_page"] == "# Article"


async def test_extract_fails_when_page_not_extracted(action, mock_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)
    mock_client = make_client(
        {"meta": {}, "data": [{"url": "https://example.com", "error": "fetch timed out"}]}
    )

    task = make_task({"url": "https://example.com"})

    with patch("zebra_tasks.web.kagi_extract.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(task, mock_context)

    assert not result.success
    assert "fetch timed out" in result.error


async def test_extract_fails_without_url(action, mock_context):
    result = await action.run(make_task({}), mock_context)
    assert not result.success
    assert "url" in result.error.lower()


async def test_extract_fails_without_api_key(action, mock_context, monkeypatch):
    monkeypatch.delenv("KAGI_API_KEY", raising=False)
    result = await action.run(make_task({"url": "https://example.com"}), mock_context)
    assert not result.success
    assert "KAGI_API_KEY" in result.error


async def test_extract_handles_http_error(action, mock_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)

    error_response = MagicMock()
    error_response.status_code = 401
    error_response.text = "Unauthorized"
    mock_client = make_client(
        side_effect=httpx.HTTPStatusError(
            "unauthorized", request=MagicMock(), response=error_response
        )
    )

    task = make_task({"url": "https://example.com"})

    with patch("zebra_tasks.web.kagi_extract.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(task, mock_context)

    assert not result.success
    assert "401" in result.error


async def test_extract_template_url(action, mock_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)
    mock_context.process.properties["target_url"] = "https://resolved.example.com"
    mock_client = make_client(MOCK_EXTRACT_RESPONSE)

    task = make_task({"url": "{{target_url}}"})

    with patch("zebra_tasks.web.kagi_extract.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(task, mock_context)

    assert result.success
    assert result.output["url"] == "https://resolved.example.com"
