"""Webhook notification task action (HTTP POST/PUT)."""

import logging
import os
from typing import Any
from urllib.parse import urlparse

import httpx
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)

_ALLOWED_METHODS = ("POST", "PUT")
_ALLOWED_SCHEMES = ("http", "https")


def _resolve_templates(value: Any, context: ExecutionContext) -> Any:
    """Resolve {{templates}} in every string inside a nested dict/list."""
    if isinstance(value, str):
        return context.resolve_template(value)
    if isinstance(value, dict):
        return {k: _resolve_templates(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_templates(v, context) for v in value]
    return value


class NotifyWebhookAction(TaskAction):
    """Send a notification to a webhook endpoint.

    Sends ``payload`` as JSON (templates resolved in every string value), or
    ``body`` as raw text. The URL defaults to ``ZEBRA_NOTIFY_WEBHOOK_URL`` so
    secret-bearing URLs (Slack, Discord, ntfy) can stay out of workflow YAML.
    Only the URL's host is reported in outputs and errors.

    Example workflow usage:
        ```yaml
        tasks:
          notify:
            name: "Post to Slack"
            action: notify_webhook
            properties:
              payload:
                text: "Goal finished: {{goal}}"
        ```

    Output:
        - status_code: HTTP status returned by the endpoint
        - host: host the notification was sent to
    """

    description = "Send a notification to a webhook URL via HTTP POST or PUT."
    reversibility_hint = "always_irreversible"

    inputs = [
        ParameterDef(
            name="url",
            type="string",
            description="Webhook URL (supports {{var}} templates); "
            "defaults to ZEBRA_NOTIFY_WEBHOOK_URL",
            required=False,
        ),
        ParameterDef(
            name="payload",
            type="dict",
            description="JSON payload; {{var}} templates resolved in string values",
            required=False,
        ),
        ParameterDef(
            name="body",
            type="string",
            description="Raw text body, used when no payload is given",
            required=False,
        ),
        ParameterDef(
            name="method",
            type="string",
            description="HTTP method: POST or PUT",
            required=False,
            default="POST",
        ),
        ParameterDef(
            name="headers",
            type="dict",
            description="Extra request headers",
            required=False,
        ),
        ParameterDef(
            name="timeout",
            type="float",
            description="Request timeout in seconds",
            required=False,
            default=15.0,
        ),
    ]

    outputs = [
        ParameterDef(name="status_code", type="int", description="HTTP status", required=True),
        ParameterDef(name="host", type="string", description="Endpoint host", required=True),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Send the webhook request."""
        url_template = task.properties.get("url") or os.environ.get("ZEBRA_NOTIFY_WEBHOOK_URL")
        if not url_template:
            return TaskResult.fail("No webhook URL: set 'url' or ZEBRA_NOTIFY_WEBHOOK_URL")
        url = context.resolve_template(str(url_template)).strip()
        parsed = urlparse(url)
        if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
            return TaskResult.fail("Webhook URL must be an http(s) URL with a host")
        host = parsed.hostname

        method = str(task.properties.get("method", "POST")).upper()
        if method not in _ALLOWED_METHODS:
            return TaskResult.fail(f"Webhook method must be one of {', '.join(_ALLOWED_METHODS)}")

        headers = {str(k): str(v) for k, v in (task.properties.get("headers") or {}).items()}
        request_kwargs: dict[str, Any] = {"headers": headers}
        payload = task.properties.get("payload")
        if payload is not None:
            request_kwargs["json"] = _resolve_templates(payload, context)
        elif task.properties.get("body") is not None:
            request_kwargs["content"] = context.resolve_template(str(task.properties["body"]))
        else:
            return TaskResult.fail("Either 'payload' or 'body' is required")

        timeout = float(task.properties.get("timeout", 15.0))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(method, url, **request_kwargs)
        except httpx.RequestError as e:
            logger.warning("Webhook notification to %s failed: %s", host, type(e).__name__)
            return TaskResult.fail(f"Network error calling webhook at {host}: {type(e).__name__}")

        if not 200 <= response.status_code < 300:
            logger.warning("Webhook %s returned %d", host, response.status_code)
            return TaskResult.fail(
                f"Webhook at {host} returned {response.status_code}: {response.text[:200]}"
            )

        logger.info("Webhook notification sent to %s (%d)", host, response.status_code)
        return TaskResult.ok(output={"status_code": response.status_code, "host": host})
