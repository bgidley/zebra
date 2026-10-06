"""Kagi page extraction task action."""

import os

import httpx
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

KAGI_EXTRACT_URL = "https://kagi.com/api/v1/extract"


class KagiExtractAction(TaskAction):
    """Extract a web page's content as markdown using the Kagi Extract API (v1).

    Fetches and cleans the content at a given URL without the caller having to
    download or parse the page. Pair with ``llm_call`` to summarise. Replaces the
    legacy ``kagi_summarize`` action (Kagi's v1 API has no summarizer endpoint).
    Requires KAGI_API_KEY.

    Example workflow usage:
        ```yaml
        tasks:
          extract:
            name: "Read page"
            action: kagi_extract
            auto: true
            properties:
              url: "{{search_results[0].url}}"
              max_chars: 20000
              output_key: page_content
        ```

    Output:
        - markdown: the extracted page content (truncated to max_chars)
        - url: the extracted URL
        - truncated: whether the content was cut to max_chars
    """

    description = "Extract a web page's content as markdown using the Kagi Extract API."
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="url",
            type="string",
            description="HTTPS URL to extract (supports {{var}} templates)",
            required=True,
        ),
        ParameterDef(
            name="max_chars",
            type="int",
            description="Maximum characters of markdown to keep",
            required=False,
            default=20000,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the markdown",
            required=False,
            default="page_content",
        ),
    ]

    outputs = [
        ParameterDef(
            name="markdown",
            type="string",
            description="The extracted page content as markdown",
            required=True,
        ),
        ParameterDef(
            name="url",
            type="string",
            description="The URL that was extracted",
            required=True,
        ),
        ParameterDef(
            name="truncated",
            type="bool",
            description="Whether the content was truncated to max_chars",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Extract a URL's content via Kagi."""
        url_template = task.properties.get("url")
        if not url_template:
            return TaskResult.fail("No URL provided")

        url = context.resolve_template(url_template).strip()
        if not url:
            return TaskResult.fail("URL resolved to empty string")

        max_chars = max(1, int(task.properties.get("max_chars", 20000)))
        output_key = task.properties.get("output_key", "page_content")

        api_key = os.environ.get("KAGI_API_KEY")
        if not api_key:
            return TaskResult.fail("KAGI_API_KEY environment variable is not set")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    KAGI_EXTRACT_URL,
                    json={"pages": [{"url": url}]},
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            return TaskResult.fail(f"Kagi API error {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            return TaskResult.fail(f"Network error calling Kagi: {e}")

        pages = data.get("data") or []
        page = pages[0] if pages else {}
        markdown = page.get("markdown")
        if markdown is None:
            reason = page.get("error") or "no content returned"
            return TaskResult.fail(f"Kagi could not extract {url}: {reason}")

        truncated = len(markdown) > max_chars
        markdown = markdown[:max_chars]

        context.set_process_property(output_key, markdown)

        return TaskResult.ok(
            output={
                "markdown": markdown,
                "url": url,
                "truncated": truncated,
            }
        )
