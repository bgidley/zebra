"""HTTP/REST client task actions (F62).

``http_get`` reads (GET/HEAD) and is always reversible; ``http_request`` writes
(POST/PUT/PATCH/DELETE) and is always irreversible, so trust gates and the golden
gym can judge them from the class hint alone. Both refuse non-public addresses
(checked again on every redirect), send named credentials only to their own host,
and cap the response body.
"""

import json
import logging
from typing import Any, ClassVar
from urllib.parse import urljoin, urlparse

import httpx
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.http.guard import Credential, HttpGuardError, check_url, load_credential
from zebra_tasks.templating import resolve_templates

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
MAX_TIMEOUT = 120.0
DEFAULT_MAX_BYTES = 1_000_000
MAX_MAX_BYTES = 5_000_000
MAX_REDIRECTS = 5

_REDIRECT_STATUSES = (301, 302, 303, 307, 308)
_HIDDEN_RESPONSE_HEADERS = ("set-cookie",)

_COMMON_INPUTS = [
    ParameterDef(
        name="url",
        type="string",
        description="http(s) URL (supports {{var}} templates); must resolve to a public address",
        required=True,
    ),
    ParameterDef(
        name="query",
        type="dict",
        description="Query parameters; {{var}} templates resolved in string values",
        required=False,
    ),
    ParameterDef(
        name="headers",
        type="dict",
        description="Extra request headers; {{var}} templates resolved",
        required=False,
    ),
    ParameterDef(
        name="credential",
        type="string",
        description="Name of a credential in ZEBRA_HTTP_CRED_<NAME> (bearer, basic or header "
        "auth); only sent to the credential's own host",
        required=False,
    ),
    ParameterDef(
        name="timeout",
        type="float",
        description=f"Request timeout in seconds (max {MAX_TIMEOUT:g})",
        required=False,
        default=DEFAULT_TIMEOUT,
    ),
    ParameterDef(
        name="max_bytes",
        type="int",
        description=f"Most response bytes to keep (max {MAX_MAX_BYTES}); the rest is cut",
        required=False,
        default=DEFAULT_MAX_BYTES,
    ),
    ParameterDef(
        name="fail_on_status",
        type="bool",
        description="Fail the task on a non-2xx status (false: return it as output)",
        required=False,
        default=True,
    ),
]

_OUTPUTS = [
    ParameterDef(name="status_code", type="int", description="HTTP status", required=True),
    ParameterDef(name="host", type="string", description="Host that answered", required=True),
    ParameterDef(name="url", type="string", description="Final URL, no query", required=True),
    ParameterDef(name="content_type", type="string", description="Response content type"),
    ParameterDef(name="headers", type="dict", description="Response headers (no cookies)"),
    ParameterDef(name="body", type="string", description="Response body as text"),
    ParameterDef(name="json", type="any", description="Parsed JSON body, or null"),
    ParameterDef(name="truncated", type="bool", description="Body was cut at max_bytes"),
]


class _RequestFailed(Exception):
    """The request could not be completed; the message is safe to show."""


def _public_url(url: str) -> str:
    """The URL without user info, query or fragment (they may carry secrets)."""
    parsed = urlparse(url)
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return f"{parsed.scheme}://{netloc}{parsed.path}"


def _decode(response: httpx.Response, content: bytes) -> str:
    try:
        return content.decode(response.charset_encoding or "utf-8", errors="replace")
    except LookupError:
        return content.decode("utf-8", errors="replace")


async def _read_body(response: httpx.Response, max_bytes: int) -> tuple[bytes, bool]:
    """Read at most ``max_bytes`` of the body; return it and whether it was cut."""
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        if size + len(chunk) > max_bytes:
            chunks.append(chunk[: max_bytes - size])
            return b"".join(chunks), True
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks), False


class _HttpAction(TaskAction):
    """Shared request logic for the HTTP actions."""

    allowed_methods: ClassVar[tuple[str, ...]] = ()
    default_method: ClassVar[str | None] = None

    def _body_kwargs(self, task: TaskInstance, context: ExecutionContext) -> dict[str, Any]:
        return {}

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Send the request and return the response."""
        props = task.properties
        method = str(props.get("method") or self.default_method or "").upper()
        if method not in self.allowed_methods:
            return TaskResult.fail(
                f"method must be one of {', '.join(self.allowed_methods)} (got {method or 'none'})"
            )
        if not props.get("url"):
            return TaskResult.fail("'url' is required")
        url = context.resolve_template(str(props["url"])).strip()

        try:
            body_kwargs = self._body_kwargs(task, context)
            credential = None
            if props.get("credential"):
                credential = load_credential(context.resolve_template(str(props["credential"])))
            host = urlparse(url).hostname or ""
            if credential and not credential.applies_to(host):
                raise HttpGuardError(
                    f"Credential '{credential.name}' may only be sent to its own host, not {host}"
                )
            return await self._send(task, context, method, url, credential, body_kwargs)
        except (HttpGuardError, _RequestFailed, ValueError) as e:
            logger.warning("HTTP %s refused or failed: %s", method, e)
            return TaskResult.fail(str(e))

    async def _send(
        self,
        task: TaskInstance,
        context: ExecutionContext,
        method: str,
        url: str,
        credential: Credential | None,
        body_kwargs: dict[str, Any],
    ) -> TaskResult:
        props = task.properties
        query = resolve_templates(props.get("query") or {}, context)
        raw_headers = resolve_templates(props.get("headers") or {}, context)
        headers = {str(k): str(v) for k, v in raw_headers.items()}
        timeout = min(float(props.get("timeout", DEFAULT_TIMEOUT)), MAX_TIMEOUT)
        max_bytes = min(int(props.get("max_bytes", DEFAULT_MAX_BYTES)), MAX_MAX_BYTES)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            for _hop in range(MAX_REDIRECTS + 1):
                host = await check_url(url)
                hop_headers = dict(headers)
                if credential and credential.applies_to(host):
                    hop_headers.update(credential.headers)
                try:
                    async with client.stream(
                        method, url, params=query or None, headers=hop_headers, **body_kwargs
                    ) as response:
                        location = response.headers.get("location")
                        if response.status_code in _REDIRECT_STATUSES and location:
                            url = urljoin(str(response.url), location)
                            query = {}
                            if response.status_code == 303 or (
                                response.status_code in (301, 302) and method not in ("GET", "HEAD")
                            ):
                                method, body_kwargs = "GET", {}
                            continue
                        content, truncated = await _read_body(response, max_bytes)
                        return self._result(response, host, content, truncated, props)
                except httpx.RequestError as e:
                    raise _RequestFailed(f"Network error calling {host}: {type(e).__name__}") from e
        raise _RequestFailed(f"Too many redirects (more than {MAX_REDIRECTS})")

    def _result(
        self,
        response: httpx.Response,
        host: str,
        content: bytes,
        truncated: bool,
        props: dict[str, Any],
    ) -> TaskResult:
        text = _decode(response, content)
        content_type = response.headers.get("content-type", "")
        parsed = None
        if "json" in content_type and not truncated and text.strip():
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
        output = {
            "status_code": response.status_code,
            "host": host,
            "url": _public_url(str(response.url)),
            "content_type": content_type,
            "headers": {
                k: v
                for k, v in response.headers.items()
                if k.lower() not in _HIDDEN_RESPONSE_HEADERS
            },
            "body": text,
            "json": parsed,
            "truncated": truncated,
        }
        logger.info("HTTP %s %s -> %d", response.request.method, host, response.status_code)
        if not response.is_success and props.get("fail_on_status", True):
            return TaskResult.fail(f"{host} returned {response.status_code}: {text[:200]}")
        return TaskResult.ok(output=output)


class HttpGetAction(_HttpAction):
    """Read from a REST API with GET or HEAD.

    Example workflow usage:
        ```yaml
        tasks:
          fetch_repo:
            name: "Fetch repo"
            action: http_get
            properties:
              url: "https://api.github.com/repos/{{owner}}/{{repo}}"
              credential: github
        ```

    Output: ``status_code``, ``host``, ``url`` (no query), ``content_type``,
    ``headers``, ``body``, ``json`` (parsed when the reply is JSON) and ``truncated``.
    """

    description = (
        "Read a web URL or REST API with HTTP GET/HEAD: query params, headers, a named "
        "credential; returns status, body text and parsed JSON. Public addresses only."
    )
    reversibility_hint = "always_reversible"
    allowed_methods = ("GET", "HEAD")
    default_method = "GET"

    inputs = _COMMON_INPUTS + [
        ParameterDef(
            name="method",
            type="string",
            description="GET or HEAD",
            required=False,
            default="GET",
        ),
    ]
    outputs = _OUTPUTS


class HttpRequestAction(_HttpAction):
    """Change something through a REST API with POST, PUT, PATCH or DELETE.

    Irreversible: put a human review or trust gate before it.

    Example workflow usage:
        ```yaml
        tasks:
          open_issue:
            name: "Open issue"
            action: http_request
            properties:
              method: POST
              url: "https://api.github.com/repos/{{owner}}/{{repo}}/issues"
              credential: github
              json:
                title: "{{issue_title}}"
        ```
    """

    description = (
        "Change something through a REST API with HTTP POST/PUT/PATCH/DELETE: JSON or text "
        "body, headers, a named credential. Irreversible: put a human review before it."
    )
    reversibility_hint = "always_irreversible"
    allowed_methods = ("POST", "PUT", "PATCH", "DELETE")

    inputs = _COMMON_INPUTS + [
        ParameterDef(
            name="method",
            type="string",
            description="POST, PUT, PATCH or DELETE",
            required=True,
        ),
        ParameterDef(
            name="json",
            type="any",
            description="JSON body; {{var}} templates resolved in string values",
            required=False,
        ),
        ParameterDef(
            name="body",
            type="string",
            description="Raw text body, used instead of json",
            required=False,
        ),
    ]
    outputs = _OUTPUTS

    def _body_kwargs(self, task: TaskInstance, context: ExecutionContext) -> dict[str, Any]:
        props = task.properties
        if props.get("json") is not None and props.get("body") is not None:
            raise ValueError("Give either 'json' or 'body', not both")
        if props.get("json") is not None:
            return {"json": resolve_templates(props["json"], context)}
        if props.get("body") is not None:
            return {"content": context.resolve_template(str(props["body"]))}
        return {}
