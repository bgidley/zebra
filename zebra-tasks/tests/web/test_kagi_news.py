"""Tests for KagiNewsFetchAction and KagiNewsReadAction (F155)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from zebra.core.models import TaskInstance, TaskState

from zebra_tasks.web.kagi_news import KagiNewsFetchAction, KagiNewsReadAction

INDEX = {
    "timestamp": 1791547294,
    "categories": [
        {"name": "World", "file": "world.json"},
        {"name": "Technology", "file": "tech.json"},
        {"name": "Sports", "file": "sports.json"},
    ],
}


def _cluster(n: int, category: str, link: str) -> dict:
    return {
        "cluster_number": n,
        "category": category,
        "title": f"{category} story {n}",
        "short_summary": f"Summary of {category} story {n}.",
        "talking_points": ["Point one", "Point two"],
        "articles": [{"link": link, "domain": "example.com"}, {"link": "http://insecure.test"}],
    }


FEEDS = {
    "https://news.kagi.com/kite.json": INDEX,
    "https://news.kagi.com/world.json": {
        "category": "World",
        "clusters": [_cluster(i, "World", f"https://w.example/{i}") for i in range(1, 4)],
    },
    "https://news.kagi.com/tech.json": {
        "category": "Technology",
        "clusters": [_cluster(1, "Technology", "https://t.example/1")],
    },
}


def make_task(properties: dict) -> TaskInstance:
    return TaskInstance(
        id="task-1",
        process_id="proc-1",
        task_definition_id="news",
        state=TaskState.RUNNING,
        foe_id="foe-1",
        properties=properties,
    )


def _response(data, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data, request=httpx.Request("GET", "https://x"))


def make_client(get=None, post=None) -> MagicMock:
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=get)
    client.post = AsyncMock(side_effect=post)
    return client


async def _feed_get(url):
    return _response(FEEDS[url])


# --- kagi_news_fetch -----------------------------------------------------------------


async def test_fetch_returns_compact_stories_for_requested_categories(mock_context):
    client = make_client(get=_feed_get)
    task = make_task({"categories": ["World", "technology"], "max_per_category": 2})

    with patch("zebra_tasks.web.kagi_news.httpx.AsyncClient", return_value=client):
        result = await KagiNewsFetchAction().run(task, mock_context)

    assert result.success
    stories = result.output["stories"]
    assert [s["id"] for s in stories] == ["world:1", "world:2", "tech:1"]
    assert result.output["categories"] == ["World", "Technology"]
    first = stories[0]
    assert first["title"] == "World story 1"
    assert first["talking_points"] == ["Point one", "Point two"]
    assert first["sources"] == ["https://w.example/1"]  # non-https links dropped
    assert mock_context.process.properties["news"]["stories"] == stories
    assert "https://news.kagi.com/sports.json" not in [c.args[0] for c in client.get.call_args_list]


async def test_fetch_unknown_categories_fails(mock_context):
    client = make_client(get=_feed_get)
    with patch("zebra_tasks.web.kagi_news.httpx.AsyncClient", return_value=client):
        result = await KagiNewsFetchAction().run(make_task({"categories": "Nope"}), mock_context)
    assert not result.success
    assert "none of the categories" in result.error


async def test_fetch_feed_outage_fails_cleanly(mock_context):
    async def down(url):
        return _response({}, status=503)

    with patch("zebra_tasks.web.kagi_news.httpx.AsyncClient", return_value=make_client(get=down)):
        result = await KagiNewsFetchAction().run(make_task({}), mock_context)
    assert not result.success
    assert "503" in result.error


async def test_fetch_network_error_fails_cleanly(mock_context):
    client = make_client(get=httpx.ConnectError("boom"))
    with patch("zebra_tasks.web.kagi_news.httpx.AsyncClient", return_value=client):
        result = await KagiNewsFetchAction().run(make_task({}), mock_context)
    assert not result.success
    assert "Network error" in result.error


# --- kagi_news_read ------------------------------------------------------------------

STORIES = [
    {
        "id": f"world:{i}",
        "category": "World",
        "title": f"Story {i}",
        "short_summary": f"Summary {i}",
        "talking_points": ["tp"],
        "sources": [f"https://w.example/{i}"],
    }
    for i in range(1, 8)
]


@pytest.fixture
def read_context(mock_context):
    mock_context.process.properties["news"] = {"stories": STORIES}
    mock_context.process.properties["picked"] = {
        "picks": [{"id": f"world:{i}", "reason": f"why {i}"} for i in (1, 2, 2, 3, 4, 5, 6)]
    }
    return mock_context


async def test_read_extracts_five_unique_picks_and_falls_back(read_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", "k")

    async def post(url, json, headers):
        pages = [
            {"url": p["url"], "markdown": f"Full text of {p['url']}"}
            if p["url"] != "https://w.example/3"
            else {"url": p["url"], "error": "paywall"}
            for p in json["pages"]
        ]
        return _response({"data": pages})

    client = make_client(post=post)
    task = make_task({"stories": "{{news}}", "picks": "{{picked}}", "max_chars": 12})

    with patch("zebra_tasks.web.kagi_news.httpx.AsyncClient", return_value=client):
        result = await KagiNewsReadAction().run(task, read_context)

    assert result.success
    articles = result.output["articles"]
    assert [a["id"] for a in articles] == ["world:1", "world:2", "world:3", "world:4", "world:5"]
    assert articles[0]["reason"] == "why 1"
    assert articles[0]["source"] == "extract"
    assert articles[0]["content"] == "Full text of"  # truncated to max_chars
    paywalled = articles[2]
    assert paywalled["source"] == "kagi_news"
    assert "Summary 3" in paywalled["content"] and "- tp" in paywalled["content"]
    assert len(client.post.call_args.kwargs["json"]["pages"]) == 5  # one batch call
    assert read_context.process.properties["articles"]["articles"] == articles


async def test_read_without_api_key_uses_summaries(read_context, monkeypatch):
    monkeypatch.delenv("KAGI_API_KEY", raising=False)
    task = make_task({"stories": "{{news}}", "picks": ["world:7"]})

    with patch("zebra_tasks.web.kagi_news.httpx.AsyncClient") as client_cls:
        result = await KagiNewsReadAction().run(task, read_context)

    client_cls.assert_not_called()
    assert result.success
    assert result.output["articles"][0]["source"] == "kagi_news"


async def test_read_extract_error_falls_back(read_context, monkeypatch):
    monkeypatch.setenv("KAGI_API_KEY", "k")
    client = make_client(post=httpx.ConnectError("down"))
    task = make_task({"stories": "{{news}}", "picks": ["world:1", "world:2"]})

    with patch("zebra_tasks.web.kagi_news.httpx.AsyncClient", return_value=client):
        result = await KagiNewsReadAction().run(task, read_context)

    assert result.success
    assert {a["source"] for a in result.output["articles"]} == {"kagi_news"}


async def test_read_no_matching_picks_fails(read_context):
    task = make_task({"stories": "{{news}}", "picks": ["tech:99"]})
    result = await KagiNewsReadAction().run(task, read_context)
    assert not result.success
