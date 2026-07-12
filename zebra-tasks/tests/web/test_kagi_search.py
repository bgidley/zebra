"""Tests for KagiSearchAction."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zebra.core.models import TaskInstance, TaskState

from zebra_tasks.web.kagi_search import KagiSearchAction

FAKE_KEY = "test-kagi-key"

MOCK_SEARCH_RESPONSE = {
    "meta": {"id": "abc", "node": "us-east"},
    "data": [
        {
            "t": 0,
            "rank": 1,
            "url": "https://example.com/article",
            "title": "Example Article",
            "snippet": "This is a snippet about the topic.",
            "published": "2024-01-01T00:00:00Z",
        },
        {
            "t": 0,
            "rank": 2,
            "url": "https://another.com/page",
            "title": "Another Page",
            "snippet": "Another snippet.",
            "published": None,
        },
        {
            "t": 1,  # related searches — should be excluded
            "list": ["related query 1", "related query 2"],
        },
    ],
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
    mock_client.get = AsyncMock(return_value=mock_response)

    task = make_task({"query": "test query", "limit": 5})

    with patch("zebra_tasks.web.kagi_search.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(task, mock_context)

    assert result.success
    assert result.output["total"] == 2  # t=1 item excluded
    assert result.output["query"] == "test query"
    results = result.output["results"]
    assert results[0]["rank"] == 1
    assert results[0]["url"] == "https://example.com/article"
    assert results[0]["title"] == "Example Article"
    assert results[1]["rank"] == 2

    # Verify API call params
    mock_client.get.assert_called_once()
    call_kwargs = mock_client.get.call_args
    assert call_kwargs.kwargs["params"]["q"] == "test query"
    assert call_kwargs.kwargs["params"]["limit"] == 5
    assert FAKE_KEY in call_kwargs.kwargs["headers"]["Authorization"]


async def test_search_stores_in_process_property(action, mock_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)

    mock_response = make_mock_response(MOCK_SEARCH_RESPONSE)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

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

    mock_response = make_mock_response({"data": []})
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    # Limit 200 should be clamped to 100
    task = make_task({"query": "test", "limit": 200})

    with patch("zebra_tasks.web.kagi_search.httpx.AsyncClient", return_value=mock_client):
        await action.run(task, mock_context)

    call_kwargs = mock_client.get.call_args
    assert call_kwargs.kwargs["params"]["limit"] == 100


async def test_search_handles_http_error(action, mock_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", FAKE_KEY)

    import httpx

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    error_response = MagicMock()
    error_response.status_code = 429
    error_response.text = "rate limited"
    mock_client.get = AsyncMock(
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

    mock_response = make_mock_response({"data": []})
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    task = make_task({"query": "{{goal}}"})

    with patch("zebra_tasks.web.kagi_search.httpx.AsyncClient", return_value=mock_client):
        result = await action.run(task, mock_context)

    assert result.success
    assert result.output["query"] == "climate change"
