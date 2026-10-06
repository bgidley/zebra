"""Tests for KagiSearchAction."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zebra.core.models import TaskInstance, TaskState

from zebra_tasks.web.kagi_search import KagiSearchAction

FAKE_KEY = "test-kagi-key"

MOCK_SEARCH_RESPONSE = {
    "meta": {"trace": "abc", "node": "us-east", "ms": 100},
    "data": {
        "search": [
            {
                "url": "https://example.com/article",
                "title": "Example Article",
                "snippet": "This is a snippet about the topic.",
                "time": "2024-01-01T00:00:00Z",
            },
            {
                "url": "https://another.com/page",
                "title": "Another Page",
                "snippet": "Another snippet.",
            },
        ],
        # non-web categories — should be excluded
        "video": [{"url": "https://video.example.com/v", "title": "A video"}],
    },
}


def make_task(properties: dict) -> TaskInstance:
    return TaskInstance(
        id="task-1",
        process_id="proc-1",
        task_definition_id="search",
        state=TaskState.RUNNING,
        foe_id="foe-1",
        properties=properties,
    )


def make_mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


@pytest.fixture
def action():
    return KagiSearchAction()


async def test_search_returns_results(action, mock_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)

    mock_response = make_mock_response(MOCK_SEARCH_RESPONSE)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    task = make_task({"query": "test query", "limit": 5})

    with patch("zebra_tasks.web.kagi_search.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(task, mock_context)

    assert result.success
    assert result.output["total"] == 2  # video results excluded
    assert result.output["query"] == "test query"
    results = result.output["results"]
    assert results[0]["rank"] == 1
    assert results[0]["url"] == "https://example.com/article"
    assert results[0]["title"] == "Example Article"
    assert results[0]["published"] == "2024-01-01T00:00:00Z"
    assert results[1]["rank"] == 2
    assert results[1]["published"] is None

    # Verify API call params
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert call_kwargs.args[0] == "https://kagi.com/api/v1/search"
    assert call_kwargs.kwargs["json"]["query"] == "test query"
    assert call_kwargs.kwargs["json"]["limit"] == 5
    assert call_kwargs.kwargs["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"


async def test_search_stores_in_process_property(action, mock_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)

    mock_response = make_mock_response(MOCK_SEARCH_RESPONSE)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    task = make_task({"query": "hello", "output_key": "my_results"})

    with patch("zebra_tasks.web.kagi_search.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(task, mock_context)

    assert result.success
    assert mock_context.process.properties.get("my_results") is not None


async def test_search_fails_without_query(action, mock_context):
    task = make_task({})
    result = await action.run(task, mock_context)
    assert not result.success
    assert "query" in result.error.lower()


async def test_search_fails_without_api_key(action, mock_context, monkeypatch):
    monkeypatch.delenv("KAGI_API_KEY", raising=False)
    task = make_task({"query": "test"})
    result = await action.run(task, mock_context)
    assert not result.success
    assert "KAGI_API_KEY" in result.error


async def test_search_clamps_limit(action, mock_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)

    mock_response = make_mock_response({"data": {"search": []}})
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    # Limit 200 should be clamped to 100
    task = make_task({"query": "test", "limit": 200})

    with patch("zebra_tasks.web.kagi_search.httpx.AsyncClient", return_value=mock_client):
        await action.run(task, mock_context)

    call_kwargs = mock_client.post.call_args
    assert call_kwargs.kwargs["json"]["limit"] == 100


async def test_search_handles_http_error(action, mock_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)

    import httpx

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    error_response = MagicMock()
    error_response.status_code = 429
    error_response.text = "rate limited"
    mock_client.post = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "rate limited", request=MagicMock(), response=error_response
        )
    )

    task = make_task({"query": "test"})

    with patch("zebra_tasks.web.kagi_search.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(task, mock_context)

    assert not result.success
    assert "429" in result.error


async def test_search_template_resolution(action, mock_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)

    mock_context.process.properties["goal"] = "climate change"

    mock_response = make_mock_response({"data": {"search": []}})
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    task = make_task({"query": "{{goal}}"})

    with patch("zebra_tasks.web.kagi_search.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(task, mock_context)

    assert result.success
    assert result.output["query"] == "climate change"


async def test_search_truncates_to_limit(action, mock_context, monkeypatch):
    """v1 limit is advisory per category, so the action enforces it itself."""
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)

    mock_response = make_mock_response(MOCK_SEARCH_RESPONSE)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    task = make_task({"query": "test", "limit": 1})

    with patch("zebra_tasks.web.kagi_search.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(task, mock_context)

    assert result.output["total"] == 1
    assert result.output["results"][0]["url"] == "https://example.com/article"


async def test_search_without_web_results(action, mock_context, monkeypatch):
    """Responses with only non-web categories (no data.search) yield zero results."""
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)

    mock_response = make_mock_response({"meta": {}, "data": {"news": [{"url": "u", "title": "t"}]}})
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("zebra_tasks.web.kagi_search.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(make_task({"query": "test"}), mock_context)

    assert result.success
    assert result.output["total"] == 0
