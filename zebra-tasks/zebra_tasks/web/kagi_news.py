"""Kagi News task actions — read the day's stories from news.kagi.com (F155).

Kagi News publishes a public JSON feed (no API key):

- ``https://news.kagi.com/kite.json`` → ``{timestamp, categories: [{name, file}]}``
- ``https://news.kagi.com/<file>`` → ``{category, timestamp, clusters: [...]}``

Each cluster is one story, summarised by Kagi from many sources, with the source
articles in ``articles[].link``.
"""

import logging
import os
from typing import Any

import httpx
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.knowledge.extract import resolve_raw
from zebra_tasks.web.kagi_extract import KAGI_EXTRACT_URL

logger = logging.getLogger(__name__)

KAGI_NEWS_BASE = "https://news.kagi.com"
DEFAULT_CATEGORIES = ["World", "Business", "Technology", "Science"]
MAX_SUMMARY_CHARS = 600
MAX_TALKING_POINTS = 4
MAX_SOURCES = 3


def _clip(text: Any, limit: int) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _story(file: str, cluster: dict[str, Any]) -> dict[str, Any]:
    """Compact, JSON-serialisable view of one Kagi News cluster."""
    stem = file.removesuffix(".json")
    sources = [
        a["link"]
        for a in cluster.get("articles") or []
        if isinstance(a, dict) and str(a.get("link", "")).startswith("https://")
    ]
    return {
        "id": f"{stem}:{cluster.get('cluster_number')}",
        "category": cluster.get("category") or stem,
        "title": _clip(cluster.get("title"), 200),
        "short_summary": _clip(cluster.get("short_summary"), MAX_SUMMARY_CHARS),
        "talking_points": [
            _clip(p, 300) for p in (cluster.get("talking_points") or [])[:MAX_TALKING_POINTS]
        ],
        "sources": sources[:MAX_SOURCES],
    }


class KagiNewsFetchAction(TaskAction):
    """Fetch today's stories from Kagi News for the given categories.

    Example workflow usage:
        ```yaml
        tasks:
          fetch_news:
            action: kagi_news_fetch
            properties:
              categories: ["World", "Technology"]
              max_per_category: 8
              output_key: news
        ```

    Output (also stored at ``output_key``):
        - stories: list of ``{id, category, title, short_summary, talking_points, sources}``
        - timestamp: feed timestamp (Unix seconds)
        - categories: category names actually fetched
    """

    description = "Fetch today's news stories from news.kagi.com (Kagi News)."
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="categories",
            type="list",
            description="Kagi News category names (default World, Business, Technology, Science)",
            required=False,
            default=DEFAULT_CATEGORIES,
        ),
        ParameterDef(
            name="max_per_category",
            type="int",
            description="Maximum stories kept per category",
            required=False,
            default=10,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the stories",
            required=False,
            default="news",
        ),
    ]

    outputs = [
        ParameterDef(name="stories", type="list", description="Compact story list", required=True),
        ParameterDef(name="timestamp", type="int", description="Feed timestamp", required=True),
        ParameterDef(
            name="categories", type="list", description="Categories fetched", required=True
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Fetch the category index, then each requested category's stories."""
        wanted = task.properties.get("categories") or DEFAULT_CATEGORIES
        if isinstance(wanted, str):
            wanted = [c.strip() for c in wanted.split(",") if c.strip()]
        wanted_lower = {c.lower() for c in wanted}
        max_per_category = max(1, int(task.properties.get("max_per_category", 10)))
        output_key = task.properties.get("output_key", "news")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                index = await self._get_json(client, f"{KAGI_NEWS_BASE}/kite.json")
                categories = [
                    c
                    for c in index.get("categories") or []
                    if isinstance(c, dict) and str(c.get("name", "")).lower() in wanted_lower
                ]
                if not categories:
                    return TaskResult.fail(f"Kagi News has none of the categories {wanted}")

                stories: list[dict[str, Any]] = []
                for category in categories:
                    data = await self._get_json(client, f"{KAGI_NEWS_BASE}/{category['file']}")
                    clusters = [c for c in data.get("clusters") or [] if isinstance(c, dict)]
                    stories += [_story(category["file"], c) for c in clusters[:max_per_category]]
        except httpx.HTTPStatusError as e:
            return TaskResult.fail(f"Kagi News error {e.response.status_code} for {e.request.url}")
        except httpx.RequestError as e:
            return TaskResult.fail(f"Network error fetching Kagi News: {e}")
        except (ValueError, KeyError, TypeError) as e:
            return TaskResult.fail(f"Unexpected Kagi News feed format: {e}")

        result = {
            "stories": stories,
            "timestamp": index.get("timestamp"),
            "categories": [c["name"] for c in categories],
        }
        context.set_process_property(output_key, result)
        logger.info("KagiNewsFetch: %d stories from %s", len(stories), result["categories"])
        return TaskResult.ok(output=result)

    @staticmethod
    async def _get_json(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError(f"{url} did not return a JSON object")
        return data


class KagiNewsReadAction(TaskAction):
    """Read picked Kagi News stories — full article where possible, Kagi's summary otherwise.

    Extracts each pick's first source link with one Kagi Extract call. A story whose
    extraction fails (paywall, no ``KAGI_API_KEY``, API error) is read from the
    Kagi News summary and talking points instead, so reading never fails the task.

    Properties:
        stories: Stories from ``kagi_news_fetch`` (list, or ``{stories: [...]}``, or template)
        picks: Story ids, or ``[{id, reason}]``, or ``{picks: [...]}`` (or template)
        max_articles: How many picks to read (default 5)
        max_chars: Characters kept per extracted article (default 6000)
        output_key: Where to store the result (default ``articles``)

    Output:
        - articles: ``[{id, title, category, url, reason, content, source}]`` where
          ``source`` is ``extract`` or ``kagi_news``
    """

    description = "Read picked Kagi News stories (Kagi Extract with summary fallback)."
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(name="stories", type="list", description="Fetched stories", required=True),
        ParameterDef(name="picks", type="list", description="Picked story ids", required=True),
        ParameterDef(
            name="max_articles",
            type="int",
            description="Maximum picks to read",
            required=False,
            default=5,
        ),
        ParameterDef(
            name="max_chars",
            type="int",
            description="Characters kept per extracted article",
            required=False,
            default=6000,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key for the articles",
            required=False,
            default="articles",
        ),
    ]

    outputs = [
        ParameterDef(name="articles", type="list", description="Articles read", required=True),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Resolve picks against stories, extract their sources, fall back to summaries."""
        props = task.properties
        output_key = props.get("output_key", "articles")
        max_articles = max(1, int(props.get("max_articles", 5)))
        max_chars = max(1, int(props.get("max_chars", 6000)))

        stories = resolve_raw(context, props.get("stories", []))
        if isinstance(stories, dict):
            stories = stories.get("stories", [])
        by_id = {s["id"]: s for s in stories or [] if isinstance(s, dict) and "id" in s}

        picks = resolve_raw(context, props.get("picks", []))
        if isinstance(picks, dict):
            picks = picks.get("picks", [])
        chosen: list[tuple[dict[str, Any], str]] = []
        for pick in picks if isinstance(picks, list) else []:
            pick_id = pick.get("id") if isinstance(pick, dict) else pick
            reason = str(pick.get("reason", "")) if isinstance(pick, dict) else ""
            story = by_id.get(str(pick_id))
            if story and all(story is not s for s, _ in chosen):
                chosen.append((story, reason))
            if len(chosen) >= max_articles:
                break
        if not chosen:
            return TaskResult.fail("None of the picked stories match the fetched stories")

        urls = [s["sources"][0] for s, _ in chosen if s.get("sources")]
        extracted = await self._extract(urls, max_chars)

        articles = []
        for story, reason in chosen:
            url = story["sources"][0] if story.get("sources") else ""
            content = extracted.get(url)
            articles.append(
                {
                    "id": story["id"],
                    "title": story["title"],
                    "category": story["category"],
                    "url": url,
                    "reason": reason,
                    "content": content or self._fallback(story),
                    "source": "extract" if content else "kagi_news",
                }
            )

        result = {"articles": articles}
        context.set_process_property(output_key, result)
        logger.info(
            "KagiNewsRead: %d articles (%d extracted)",
            len(articles),
            sum(a["source"] == "extract" for a in articles),
        )
        return TaskResult.ok(output=result)

    @staticmethod
    def _fallback(story: dict[str, Any]) -> str:
        points = "\n".join(f"- {p}" for p in story.get("talking_points") or [])
        return f"{story.get('short_summary', '')}\n\n{points}".strip()

    @staticmethod
    async def _extract(urls: list[str], max_chars: int) -> dict[str, str]:
        """Return ``{url: markdown}`` for the pages Kagi could extract; never raises."""
        api_key = os.environ.get("KAGI_API_KEY")
        if not urls or not api_key:
            if urls:
                logger.info("KagiNewsRead: no KAGI_API_KEY — using Kagi News summaries")
            return {}
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    KAGI_EXTRACT_URL,
                    json={"pages": [{"url": u} for u in urls]},
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("KagiNewsRead: extract failed — using summaries: %s", e)
            return {}

        pages = data.get("data") if isinstance(data, dict) else None
        result = {}
        for i, page in enumerate(pages or []):
            if not isinstance(page, dict) or not page.get("markdown"):
                continue
            url = page.get("url") or (urls[i] if i < len(urls) else "")
            result[url] = page["markdown"][:max_chars]
        return result
