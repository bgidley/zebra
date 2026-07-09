"""Kagi URL summarizer task action."""

import os

import httpx
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

KAGI_SUMMARIZE_URL = "https://kagi.com/api/v0/summarize"


class KagiSummarizeAction(TaskAction):
    """Summarize a web page using the Kagi Summarizer API.

    Fetches and summarizes the content at a given URL without the caller
    having to download or parse the page. Requires KAGI_API_KEY.

    Example workflow usage:
        ```yaml
        tasks:
          summarize:
            name: "Summarize page"
            action: kagi_summarize
            auto: true
            properties:
              url: "{{search_results[0].url}}"
              summary_type: takeaway
              output_key: page_summary
        ```

    Output:
        - summary: the text summary
        - url: the summarized URL
        - tokens: token count used by Kagi's summarizer
    """

    description = "Summarize a web page using the Kagi Summarizer API."
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="url",
            type="string",
            description="URL to summarize (supports {{var}} templates)",
            required=True,
        ),
        ParameterDef(
            name="engine",
            type="string",
            description="Summarizer engine: agnes (default), daphne, muriel, or cecil",
            required=False,
            default="agnes",
        ),
        ParameterDef(
            name="summary_type",
            type="string",
            description="Output style: summary (default) or takeaway (bullet points)",
            required=False,
            default="summary",
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the summary text",
            required=False,
            default="page_summary",
        ),
    ]

    outputs = [
        ParameterDef(
            name="summary",
            type="string",
            description="The generated summary text",
            required=True,
        ),
        ParameterDef(
            name="url",
            type="string",
            description="The URL that was summarized",
            required=True,
        ),
        ParameterDef(
            name="tokens",
            type="int",
            description="Token count used by Kagi's summarizer",
            required=False,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Summarize a URL via Kagi."""
        url_template = task.properties.get("url")
        if not url_template:
            return TaskResult.fail("No URL provided")

        url = context.resolve_template(url_template)
        if not url.strip():
            return TaskResult.fail("URL resolved to empty string")

        engine = task.properties.get("engine", "agnes")
        summary_type = task.properties.get("summary_type", "summary")
        output_key = task.properties.get("output_key", "page_summary")

        api_key = os.environ.get("KAGI_API_KEY")
        if not api_key:
            return TaskResult.fail("KAGI_API_KEY environment variable is not set")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(
                    KAGI_SUMMARIZE_URL,
                    params={"url": url, "engine": engine, "summary_type": summary_type},
                    headers={"Authorization": f"Bot {api_key}"},
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            return TaskResult.fail(f"Kagi API error {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            return TaskResult.fail(f"Network error calling Kagi: {e}")

        result_data = data.get("data") or {}
        summary = result_data.get("output", "")
        tokens = result_data.get("tokens")

        context.set_process_property(output_key, summary)

        return TaskResult.ok(
            output={
                "summary": summary,
                "url": url,
                "tokens": tokens,
            }
        )
