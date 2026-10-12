"""Tests for the redesigned key screens (#162): home, trust, workflow detail, run goal."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory
from zebra.core.models import ProcessDefinition, RoutingDefinition, TaskDefinition
from zebra_agent.metrics import WorkflowStats
from zebra_agent_web.api import web_views
from zebra_agent_web.api.web_views import _budget_bars, _workflow_structure

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
LEVELS = ["SUPERVISED", "SEMI_AUTONOMOUS", "AUTONOMOUS"]


def _page(template: str, context: dict, path: str = "/") -> str:
    user = get_user_model().objects.create_user(username=f"u{abs(hash(path)) % 10**8}")
    request = RequestFactory().get(path)
    request.user = user
    return render_to_string(template, {"user": user, **context}, request=request)


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------


def _activity(goal, awaiting, task_id=None):
    return {
        "goal": goal,
        "run_id": f"run-{goal}",
        "workflow_name": "Weekly Digest",
        "current_tasks": ["Review"],
        "started_at": datetime.now(UTC) - timedelta(minutes=12),
        "cost": 0.4123,
        "awaiting_human": awaiting,
        "human_task_id": task_id,
    }


def _home_context(**overrides):
    running = [_activity("waiting", True, "ht-1"), _activity("busy", False)]
    base = {
        "running_activities": running,
        "needs_you": [a for a in running if a["awaiting_human"]],
        "running_count": len(running),
        "workflows_count": 18,
        "total_runs": 36,
        "success_rate": "86%",
        "budget": {
            "daily_budget": 50.0,
            "spent_today": 7.42,
            "remaining": 42.58,
            "paced_allowance": 31.11,
            "available": 23.69,
            "pct_used": "14.8%",
            "reset_hour": 0,
            "queue_depth": 3,
            **_budget_bars({"daily_budget": 50.0, "spent_today": 7.42, "paced_allowance": 31.11}),
        },
        "trust_levels": [
            {"domain": "code", "level": "SEMI_AUTONOMOUS"},
            {"domain": "finance", "level": "SUPERVISED"},
        ],
        "on_my_mind": [],
        "recent_runs": [],
        "top_workflows": [],
    }
    return {**base, **overrides}


def test_home_leads_with_needs_you(db):
    html = _page("pages/dashboard.html", _home_context())
    needs = html.split('data-testid="needs-you"', 1)[1].split("</section>", 1)[0]

    assert html.index('data-testid="needs-you"') < html.index('data-testid="vitals"')
    assert "waiting" in needs and 'href="/tasks/ht-1/"' in needs
    assert "busy" not in needs


def test_home_hides_needs_you_when_nothing_waits(db):
    html = _page("pages/dashboard.html", _home_context(needs_you=[]))

    assert 'data-testid="needs-you"' not in html


def test_home_vitals_show_spend_success_and_queue(db):
    html = _page("pages/dashboard.html", _home_context())
    vitals = html.split('data-testid="vitals"', 1)[1].split("</section>", 1)[0]

    assert "$7.42" in vitals and "$50.00" in vitals
    assert "86%" in vitals and "36 runs" in vitals
    assert re.search(r">\s*3\s*<span[^>]*>queued", vitals)
    assert "width: 14.8%" in vitals  # spent
    assert "width: 62.2%" in vitals  # paced allowance band


def test_home_vitals_degrade_without_budget(db):
    html = _page("pages/dashboard.html", _home_context(budget=None))

    assert "Budget unavailable" in html


def test_home_has_no_stat_tiles(db):
    html = _page("pages/dashboard.html", _home_context())

    assert "Total Runs" not in html
    assert not (TEMPLATES / "components" / "stat_card.html").exists()


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (
            {"daily_budget": 50, "spent_today": 7.42, "paced_allowance": 31.11},
            {"spent_pct": 14.8, "paced_pct": 62.2, "over_pace": False},
        ),
        (
            {"daily_budget": 10, "spent_today": 12, "paced_allowance": 5},
            {"spent_pct": 100.0, "paced_pct": 50.0, "over_pace": True},
        ),
        (
            {"daily_budget": 0, "spent_today": 1, "paced_allowance": 0},
            {"spent_pct": 0.0, "paced_pct": 0.0, "over_pace": True},
        ),
        ({"daily_budget": "bad"}, {"spent_pct": 0.0, "paced_pct": 0.0, "over_pace": False}),
    ],
)
def test_budget_bars(status, expected):
    assert _budget_bars(status) == expected


# ---------------------------------------------------------------------------
# Trust
# ---------------------------------------------------------------------------


def _trust_context(**overrides):
    base = {
        "domains": [
            {"domain": "code", "level": "SEMI_AUTONOMOUS"},
            {"domain": "finance", "level": "SUPERVISED"},
        ],
        "trust_levels": LEVELS,
        "pending_suggestions": [],
        "changes": [],
        "resolved_suggestions": [],
        "freeing_enabled": False,
        "is_freed": False,
    }
    return {**base, **overrides}


def test_trust_domains_are_one_form_per_row_with_level_radios(db):
    html = _page("pages/trust.html", _trust_context(), path="/trust/")
    table = html.split('data-testid="trust-domains"', 1)[1].split("</section>", 1)[0]
    forms = re.findall(r'<form method="post" action="/trust/([a-z]+)/set/".*?</form>', table, re.S)

    assert forms == ["code", "finance"]
    code_form = re.search(r'action="/trust/code/set/".*?</form>', table, re.S).group(0)
    radios = re.findall(r'type="radio" name="level" value="([A-Z_]+)"[^>]*?(checked)?>', code_form)
    assert [v for v, _ in radios] == LEVELS
    assert [v for v, checked in radios if checked] == ["SEMI_AUTONOMOUS"]
    assert 'name="reason"' in code_form
    assert "Semi-autonomous" in code_form


def test_trust_override_is_guarded_outline_button(db):
    html = _page("pages/trust.html", _trust_context(), path="/trust/")
    button = re.search(r'<button[^>]*data-testid="pause-all"[^>]*>', html).group(0)

    assert "btn-danger" in button
    assert "confirm(" in html.split('action="/trust/pause-all/"', 1)[1].split(">", 1)[0]


def test_trust_override_hidden_once_freed(db):
    html = _page("pages/trust.html", _trust_context(is_freed=True), path="/trust/")

    assert 'data-testid="pause-all"' not in html


def test_trust_suggestion_evidence_reads_as_zebra(db):
    suggestion = {
        "id": "s1",
        "domain": "scheduling",
        "to_level": "SEMI_AUTONOMOUS",
        "evidence": "Completed 20 scheduling tasks",
        "created_at": None,
    }
    html = _page(
        "pages/trust.html", _trust_context(pending_suggestions=[suggestion]), path="/trust/"
    )
    block = html.split('data-testid="pending-suggestions"', 1)[1].split("</section>", 1)[0]

    assert "Pending Agent Suggestions" in block
    assert "Zebra's evidence" in block and "Completed 20 scheduling tasks" in block
    assert "promote to Semi-autonomous" in block


# ---------------------------------------------------------------------------
# Workflow detail
# ---------------------------------------------------------------------------


def _definition():
    tasks = {
        "gather": TaskDefinition(id="gather", name="Gather", action="llm_call"),
        "ask": TaskDefinition(id="ask", name="Ask you", auto=False),
        "merge": TaskDefinition(id="merge", name="Merge", action="merge", synchronized=True),
        "orphan": TaskDefinition(id="orphan", name="Orphan"),
    }
    routings = [
        RoutingDefinition(id="r1", source_task_id="gather", dest_task_id="ask"),
        RoutingDefinition(id="r2", source_task_id="ask", dest_task_id="merge"),
    ]
    return ProcessDefinition(
        id="wf", name="Digest", first_task_id="gather", tasks=tasks, routings=routings
    )


class _Library:
    def __init__(self, definition=None):
        self.definition = definition

    def get_workflow(self, name):
        if self.definition is None:
            raise ValueError(name)
        return self.definition

    def get_workflow_yaml(self, name):
        return "name: Digest\n" + "# line\n" * 300

    async def list_workflows(self):
        class Info:
            description = "Weekly digest"
            tags = ["writing"]
            retired = None

        info = Info()
        info.name = "Digest"
        return [info]


def test_workflow_structure_orders_steps_along_routings():
    structure = _workflow_structure(_Library(_definition()), "Digest")

    assert [s["id"] for s in structure["steps"]] == ["gather", "ask", "merge", "orphan"]
    assert structure["steps"][1]["human"] is True
    assert structure["steps"][2]["synchronized"] is True
    assert structure["diagram_svg"].startswith("<svg")


def test_workflow_structure_fails_soft():
    assert _workflow_structure(_Library(None), "Missing") == {"diagram_svg": None, "steps": []}


@pytest.mark.django_db(transaction=True)
async def test_workflow_detail_puts_steps_first_and_yaml_in_disclosure(monkeypatch):
    import zebra_agent_web.api.agent_engine as agent_engine_module

    class _Metrics:
        async def get_stats(self, name):
            return WorkflowStats(workflow_name=name, total_runs=2, successful_runs=2)

    async def _noop():
        return None

    monkeypatch.setattr(agent_engine_module, "ensure_initialized", _noop)
    monkeypatch.setattr(agent_engine_module, "get_library", lambda: _Library(_definition()))
    monkeypatch.setattr(agent_engine_module, "get_metrics", lambda: _Metrics())
    from asgiref.sync import sync_to_async

    user = await sync_to_async(get_user_model().objects.create_user)(username="wf-user")
    request = RequestFactory().get("/workflows/Digest/")
    request.user = user

    html = (await web_views.workflow_detail(request, "Digest")).content.decode()

    assert html.index('data-testid="workflow-steps"') < html.index(
        'data-testid="workflow-definition"'
    )
    assert 'data-testid="workflow-diagram"' in html
    definition = html.split('data-testid="workflow-definition"', 1)[0].rsplit("<", 1)[1]
    assert definition.startswith("details")
    assert "needs you" in html and "waits for branches" in html


# ---------------------------------------------------------------------------
# Run goal and run pages
# ---------------------------------------------------------------------------


def test_run_goal_keeps_form_contract():
    source = (TEMPLATES / "pages" / "run_goal.html").read_text()

    for hook in (
        'id="goal-form"',
        'hx-post="/run/execute/"',
        'hx-target="#result-container"',
        'hx-indicator="#loading-indicator"',
        'hx-post="/run/queue/"',
        'hx-include="#goal-form"',
        'id="loading-indicator"',
        'id="prev-run-preview"',
        'onchange="loadRunContext(this.value)"',
        'id="result-container"',
    ):
        assert hook in source, hook
    for field in ("goal", "model", "priority", "deadline", "previous_run_id"):
        assert f'name="{field}"' in source, field
    assert 'rows="6"' in source


@pytest.mark.parametrize("page", ["run_detail.html", "run_pending.html"])
def test_run_page_task_headers_shrink_on_phones(page):
    source = (TEMPLATES / "pages" / page).read_text()

    assert (
        '<span class="min-w-0 truncate font-medium text-white">{{ task.task_name }}</span>'
        in source
    )
    assert (
        '<span class="hidden sm:inline truncate text-sm text-gray-500">({{ task.task_id }})</span>'
        in (source)
    )
    assert '<span class="font-medium text-white">{{ task.task_name }}</span>' not in source


@pytest.mark.parametrize(
    "page", ["dashboard.html", "trust.html", "workflow_detail.html", "run_goal.html"]
)
def test_key_screens_have_no_em_dashes(page):
    source = (TEMPLATES / "pages" / page).read_text()

    assert "—" not in source and "&mdash;" not in source


def test_workflow_diagram_draws_at_natural_width():
    svg = _workflow_structure(_Library(_definition()), "Digest")["diagram_svg"]

    assert "max-width: none" in svg
    assert "max-width: 100%" not in svg
    width = re.search(r'viewBox="0 0 ([\d.]+) ', svg).group(1)
    assert f'width="{width}"' in svg


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(seconds=20), "now"),
        (timedelta(minutes=12), "12m ago"),
        (timedelta(hours=3, minutes=40), "3h ago"),
        (timedelta(days=1, hours=7), "1d ago"),
    ],
)
def test_ago_filter_uses_one_unit(delta, expected):
    from zebra_agent_web.api.templatetags.format_tags import ago

    assert ago(datetime.now(UTC) - delta) == expected


def test_ago_filter_handles_empty():
    from zebra_agent_web.api.templatetags.format_tags import ago

    assert ago(None) == "" and ago("yesterday") == ""


def test_ago_filter_treats_future_as_now():
    from zebra_agent_web.api.templatetags.format_tags import ago

    assert ago(datetime.now(UTC) + timedelta(minutes=5)) == "now"


def test_workflow_structure_survives_routing_cycles():
    definition = _definition()
    loop = RoutingDefinition(id="r3", source_task_id="merge", dest_task_id="gather")
    looped = definition.model_copy(update={"routings": [*definition.routings, loop]})

    steps = _workflow_structure(_Library(looped), "Digest")["steps"]

    assert [s["id"] for s in steps] == ["gather", "ask", "merge", "orphan"]
