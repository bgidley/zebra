"""Tests for the /dreams/ Dream Cycle history page."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from zebra_agent_web.api import dream_history
from zebra_agent_web.api.models import (
    ProcessDefinitionModel,
    ProcessInstanceModel,
    RoutineRunModel,
)

T0 = datetime(2026, 10, 8, 3, 0, tzinfo=UTC)

FULL_PROPS = {
    "metrics_analysis": {
        "analysis_period_days": 7,
        "total_runs_analyzed": 42,
        "unique_workflows": 6,
        "low_performers": [{"workflow_name": "Flaky Flow", "success_rate": 0.2}],
        "high_performers": [{"workflow_name": "Solid Flow", "success_rate": 0.95}],
        "continuation_analysis": {
            "total_continuations": 3,
            "top_continued": [{"workflow_name": "Research Topic", "count": 2}],
            "capability_gaps": [{"original_workflow": "x"}],
        },
    },
    "evaluation": {
        "overall_assessment": {
            "health_score": "72",
            "summary": "Mostly healthy",
            "key_issues": ["Flaky Flow times out"],
        }
    },
    "optimization_results": {
        "changes_made": [{"type": "modify", "workflow": "Flaky Flow", "action": "Add retry"}],
        "failed_changes": [{"type": "create", "workflow": "Bad Idea", "reason": "invalid YAML"}],
        "dry_run": False,
    },
    "curation": {
        "retired": [
            {
                "workflow": "Old Flow",
                "rule": "unused",
                "reason": "not used in 30 days",
                "superseded_by": None,
                "applied": True,
            }
        ],
        "deferred": [],
        "dry_run": False,
    },
    "dream_summary": "System health is **good**.",
}


@pytest.fixture
def completed_setup(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


def _definition(name: str, def_id: str) -> None:
    ProcessDefinitionModel.objects.create(id=def_id, name=name, data="{}")


def _process(pid: str, def_id: str, state: str, props: dict, started: datetime) -> None:
    ProcessInstanceModel.objects.create(
        id=pid,
        definition_id=def_id,
        state=state,
        properties=json.dumps(props),
        created_at=started,
        updated_at=started,
        completed_at=started + timedelta(minutes=2, seconds=5) if state == "complete" else None,
    )


@pytest.mark.django_db
def test_summarize_cycle_flattens_step_reports():
    _definition(dream_history.DREAM_CYCLE_WORKFLOW, "dream-v5")
    _process("p1", "dream-v5", "complete", FULL_PROPS, T0)

    (cycle,) = dream_history.recent_dream_cycles()

    assert cycle["health_score"] == 72
    assert cycle["runs_analyzed"] == 42
    assert cycle["duration"] == "2m 5s"
    assert cycle["low_performers"] == ["Flaky Flow"]
    assert [c["workflow"] for c in cycle["changes_made"]] == ["Flaky Flow"]
    assert cycle["retired_applied"] == 1
    assert cycle["continuations"] == 3
    assert cycle["capability_gaps"] == 1
    assert cycle["summary"] == "System health is **good**."


@pytest.mark.django_db
def test_recent_dream_cycles_only_returns_dream_cycle_processes_newest_first():
    _definition(dream_history.DREAM_CYCLE_WORKFLOW, "dream-v4")
    _definition(dream_history.DREAM_CYCLE_WORKFLOW, "dream-v5")
    _definition("Agent Main Loop", "main")
    _process("old", "dream-v4", "complete", {}, T0 - timedelta(days=1))
    _process("new", "dream-v5", "failed", {"__error__": "boom"}, T0)
    _process("goal", "main", "complete", {}, T0)

    cycles = dream_history.recent_dream_cycles()

    assert [c["id"] for c in cycles] == ["new", "old"]
    assert cycles[0]["error"] == "boom"
    assert cycles[1]["health_score"] is None


@pytest.mark.django_db
def test_page_renders_cycles_and_schedule(authenticated_client, completed_setup):
    _definition(dream_history.DREAM_CYCLE_WORKFLOW, "dream-v5")
    _process("p1", "dream-v5", "complete", FULL_PROPS, T0)
    _process(
        "p2",
        "dream-v5",
        "failed",
        {"__error__": "LLM provider unavailable", "__failed_task__": "evaluate_workflows"},
        T0 + timedelta(days=1),
    )
    RoutineRunModel.objects.create(
        routine_name="dream_cycle", next_run=T0 + timedelta(days=2), last_status="ok"
    )

    response = authenticated_client.get("/dreams/")

    assert response.status_code == 200
    html = response.content.decode()
    assert "Health 72/100" in html
    assert "<strong>good</strong>" in html
    assert "Old Flow" in html
    assert "invalid YAML" in html
    assert "LLM provider unavailable" in html
    assert "evaluate_workflows" in html
    assert "2026-10-10 03:00" in html


@pytest.mark.django_db
def test_page_empty_state(authenticated_client, completed_setup):
    response = authenticated_client.get("/dreams/")

    assert response.status_code == 200
    assert "No dream cycles have run yet." in response.content.decode()
