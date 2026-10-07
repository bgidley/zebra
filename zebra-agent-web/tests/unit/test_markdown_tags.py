"""Tests for the server-side ``markdown`` template filter (#149).

Run detail renders the Final Output with this filter so markdown displays as
HTML without depending on a client-side library.
"""

from datetime import UTC, datetime

import pytest
from asgiref.sync import sync_to_async
from django.template import Context, Template
from zebra_agent_web.api.templatetags.markdown_tags import render_markdown


def test_renders_markdown_to_html():
    html = render_markdown(
        "# Title\n\nSome **bold** and a [link](https://example.com).\n\n- a\n- b"
    )

    assert "<h1>Title</h1>" in html
    assert "<strong>bold</strong>" in html
    assert '<a href="https://example.com">link</a>' in html
    assert "<li>a</li>" in html


def test_renders_gfm_tables():
    html = render_markdown("| a | b |\n|---|---|\n| 1 | 2 |")

    assert "<table>" in html
    assert "<td>1</td>" in html


def test_escapes_raw_html():
    html = render_markdown("hi <script>alert(1)</script> <img src=x onerror=alert(1)>")

    assert "<script>" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html


def test_rejects_javascript_links():
    html = render_markdown("[click](javascript:alert(1))")

    assert 'href="javascript:' not in html


def test_json_output_shown_as_preformatted_block():
    html = render_markdown('{"answer": "<b>42</b>", "items": [1, 2]}')

    assert html.startswith("<pre><code>")
    assert "<b>" not in html
    assert "&lt;b&gt;42&lt;/b&gt;" in html


def test_empty_values_render_nothing():
    assert render_markdown(None) == ""
    assert render_markdown("") == ""


def test_filter_registered_for_templates():
    out = Template("{% load markdown_tags %}{{ text|markdown }}").render(
        Context({"text": "## Heading"})
    )

    assert "<h2>Heading</h2>" in out


class _StubMetricsStore:
    def __init__(self, run):
        self._run = run

    async def get_run(self, run_id):
        return self._run if run_id == self._run.id else None

    async def get_task_executions(self, run_id):
        return []


class _StubLibrary:
    def get_workflow(self, name):
        raise ValueError(name)


@pytest.mark.django_db(transaction=True)
async def test_run_detail_renders_final_output_markdown(monkeypatch):
    """The run detail page renders the Final Output markdown as HTML server-side."""
    import zebra_agent_web.api.agent_engine as agent_engine_module
    import zebra_agent_web.api.engine as engine_module
    from django.contrib.auth import get_user_model
    from django.test import AsyncClient
    from zebra.core.engine import WorkflowEngine
    from zebra.storage.memory import InMemoryStore
    from zebra.tasks.registry import ActionRegistry
    from zebra_agent.metrics import WorkflowRun
    from zebra_agent_web.api.identity import set_identity_sync

    run = WorkflowRun(
        id="run-md",
        workflow_name="Web Research",
        goal="Plan a holiday",
        started_at=datetime(2026, 10, 7, tzinfo=UTC),
        completed_at=datetime(2026, 10, 7, tzinfo=UTC),
        success=True,
        output="# Plan\n\nBook **early**: <script>alert(1)</script>",
    )
    store = InMemoryStore()
    monkeypatch.setattr(engine_module, "_store", store)
    monkeypatch.setattr(engine_module, "_engine", WorkflowEngine(store, ActionRegistry()))
    monkeypatch.setattr(agent_engine_module, "_metrics", _StubMetricsStore(run))
    monkeypatch.setattr(agent_engine_module, "_library", _StubLibrary())
    await sync_to_async(set_identity_sync)("Test User")
    user = await sync_to_async(get_user_model().objects.create_user)(username="testuser")
    client = AsyncClient()
    await sync_to_async(client.force_login)(user)

    response = await client.get("/runs/run-md/")

    html = response.content.decode()
    assert response.status_code == 200
    assert "<h1>Plan</h1>" in html
    assert "<strong>early</strong>" in html
    assert "<script>alert(1)</script>" not in html
    assert "marked.min.js" not in html
