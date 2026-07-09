"""Kagi web search task action."""

import os

import httpx
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

KAGI_SEARCH_URL = "https://kagi.com/api/v0/search"


class KagiSearchAction(TaskAction):
    """Search the web using the Kagi Search API.

    Returns ranked search results (title, URL, snippet) for a given query.
    Requires KAGI_API_KEY environment variable.

    Example workflow usage:
        ```yaml
        tasks:
          search:
            name: "Search the web"
            action: kagi_search
            auto: true
            properties:
              query: "{{goal}}"
              limit: 5
              output_key: search_results
        ```

    Output:
        - results: list of {rank, url, title, snippet, published}
        - query: the resolved query string
        - total: number of results returned
    """

    description = "Search the web using Kagi and return ranked results."
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="query",
            type="string",
            description="Search query (supports {{var}} templates)",
            required=True,
        ),
        ParameterDef(
            name="limit",
            type="int",
            description="Maximum number of results to return (1–100)",
            required=False,
            default=10,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the results list",
            required=False,
            default="search_results",
        ),
    ]

    outputs = [
        ParameterDef(
            name="results",
            type="list",
            description="Ranked search results, each with rank/url/title/snippet",
            required=True,
        ),
        ParameterDef(
            name="query",
            type="string",
            description="The resolved search query",
            required=True,
        ),
        ParameterDef(
            name="total",
            type="int",
            description="Number of results returned",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Execute a Kagi web search."""
        query_template = task.properties.get("query")
        if not query_template:
            return TaskResult.fail("No query provided")

        query = context.resolve_template(query_template)
        if not query.strip():
            return TaskResult.fail("Query resolved to empty string")

        limit = int(task.properties.get("limit", 10))
        limit = max(1, min(100, limit))
        output_key = task.properties.get("output_key", "search_results")

        api_key = os.environ.get("KAGI_API_KEY")
        if not api_key:
            return TaskResult.fail("KAGI_API_KEY environment variable is not set")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    KAGI_SEARCH_URL,
                    params={"q": query, "limit": limit},
                    headers={"Authorization": f"Bot {api_key}"},
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            return TaskResult.fail(f"Kagi API error {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            return TaskResult.fail(f"Network error calling Kagi: {e}")

        raw_items = data.get("data") or []
        results = [
            {
                "rank": item.get("rank"),
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "published": item.get("published"),
            }
            for item in raw_items
            if item.get("t") == 0  # t=0 are search results; t=1 are related searches
        ]

        context.set_process_property(output_key, results)

        return TaskResult.ok(
            output={
                "results": results,
                "query": query,
                "total": len(results),
            }
        )
