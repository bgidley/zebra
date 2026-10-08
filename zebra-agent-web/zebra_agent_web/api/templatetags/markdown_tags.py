"""Template filter for rendering LLM/workflow output markdown as HTML server-side.

Usage in templates::

    {% load markdown_tags %}
    {{ run.output|markdown }}

Rendering happens on the server so output displays correctly without a
client-side markdown library. Raw HTML in the source is escaped and unsafe
link schemes (``javascript:`` etc.) are rejected by markdown-it, so the result
is safe to mark as such even though the content is LLM-generated.
"""

import json

from django import template
from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe
from markdown_it import MarkdownIt

register = template.Library()

# CommonMark + GFM tables/strikethrough; html=False escapes any raw HTML.
_md = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable(["table", "strikethrough"])


@register.filter(name="markdown")
def render_markdown(value: object) -> SafeString:
    """Render a markdown string to safe HTML.

    Structured output (a JSON object/array, or a string containing one) is
    shown as a preformatted JSON block instead, since markdown would mangle it.
    """
    if value is None or value == "":
        return mark_safe("")

    structured = value if isinstance(value, (dict, list)) else None
    if structured is None:
        text = str(value)
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, (dict, list)):
            structured = parsed
    if structured is not None:
        dumped = json.dumps(structured, indent=2, ensure_ascii=False)
        return mark_safe(f"<pre><code>{escape(dumped)}</code></pre>")

    return mark_safe(_md.render(text))
