"""The outcome ruling form, generated per disputed outcome, in the web UI (#295).

Parks a real *Outcome Review* (the shipped YAML) on its human ruling with the result the
compare and brief steps leave, then renders and submits the task page.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskInstance, TaskState
from zebra.definitions.loader import load_definition_from_yaml
from zebra.tasks.registry import ActionRegistry
from zebra_agent_web.api import agent_engine
from zebra_agent_web.api import engine as engine_module
from zebra_tasks.agent.outcome_review import (
    CompareOutcomeReviewsAction,
    compare_reviews,
    outcome_texts,
    parse_review,
)
from zebra_tasks.agent.outcome_review import ruling_form as build_form

YAML = Path(__file__).parents[3] / "zebra-agent" / "workflows" / "outcome_review.yaml"
OUTCOMES = "| O1 | Scans every added line | test |\n| O2 | Fails closed | test |"
ZEBRA = {
    "verdicts": [
        {"id": "O1", "verdict": "partial", "evidence": "Lock lines skip PII rules (scan.py:655)."},
        {"id": "O2", "verdict": "met", "evidence": "scan.py:487 fails closed."},
    ]
}
CLAUDE = {
    "verdicts": [
        {"id": "O1", "verdict": "met", "evidence": "test_each_rule_rejects covers every rule."},
        {"id": "O2", "verdict": "met", "evidence": "test_empty_diff_fails_closed."},
    ]
}
BRIEF = {
    "O1": {
        "crux": "Whether lock-file lines are scanned for personal data",
        "zebra": "They are not: scan.py:673-681 runs only secret rules on them.",
        "claude": "Did not address lock files; every rule is tested on ordinary lines.",
        "settle": "Read scan.py:655-697.",
    }
}


@pytest.fixture
def identity(transactional_db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
def wf_engine(monkeypatch):
    from zebra_agent_web.storage import DjangoStore

    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("compare_outcome_reviews", CompareOutcomeReviewsAction)
    store = DjangoStore()
    wf = WorkflowEngine(store, registry)
    monkeypatch.setattr(engine_module, "_store", store)
    monkeypatch.setattr(engine_module, "_engine", wf)

    async def _noop():
        return None

    monkeypatch.setattr(agent_engine, "ensure_initialized", _noop)
    monkeypatch.setattr(
        agent_engine, "get_agent_loop", lambda: SimpleNamespace(engine=wf, goal_timeout=60.0)
    )
    return wf


async def _park_ruling(wf: WorkflowEngine) -> tuple[str, str]:
    """An Outcome Review waiting on its ruling, as compare_again + brief_disputes leave it."""
    definition = load_definition_from_yaml(YAML.read_text())
    await wf.store.save_definition(definition)
    texts = outcome_texts(OUTCOMES)
    result = compare_reviews(parse_review(ZEBRA), parse_review(CLAUDE), set(texts), texts)
    result["briefs"] = BRIEF
    result["ruling_form"] = build_form(result["rows"], texts, BRIEF, "#282 Diff scan (abc1234)")
    process = await wf.create_process(
        definition,
        properties={
            "issue": "282",
            "title": "Diff scan",
            "deployed_hash": "abc1234",
            "outcomes": OUTCOMES,
            "zebra_review": ZEBRA,
            "claude_review": CLAUDE,
            "review_result": result,
        },
    )
    running = await wf.store.load_process(process.id)
    await wf.store.save_process(running.model_copy(update={"state": ProcessState.RUNNING}))
    task = TaskInstance(
        id="ruling-v6",
        task_definition_id="human_ruling",
        process_id=process.id,
        state=TaskState.READY,
        foe_id="foe-v6",
    )
    await wf.store.save_task(task)
    return process.id, task.id


@pytest.mark.django_db(transaction=True)
async def test_the_ruling_page_shows_the_crux_and_a_pick_per_disputed_outcome(
    wf_engine, identity, authenticated_async_client
):
    _, task_id = await _park_ruling(wf_engine)

    response = await authenticated_async_client.get(f"/tasks/{task_id}/")
    content = response.content.decode()

    assert response.status_code == 200
    assert "Zebra and Claude disagree on 1 of 2 outcomes" in content
    assert "#282 Diff scan (abc1234)" in content
    assert "<strong>In dispute:</strong> Whether lock-file lines are scanned" in content
    assert "Summary by a low-tier model, not a verdict" in content
    assert '<select id="field_O1" name="O1"' in content and "required" in content
    assert ">Partial (Zebra)</option>" in content and ">Met (Claude)</option>" in content
    assert "O2 met" in content  # agreed outcomes in one line
    assert 'name="O2"' not in content  # no pick for an agreed outcome
    assert "Full evidence" in content and "test_each_rule_rejects" in content


@pytest.mark.django_db(transaction=True)
async def test_a_ruling_needs_a_pick_then_records_it_per_outcome(
    wf_engine, identity, authenticated_async_client
):
    process_id, task_id = await _park_ruling(wf_engine)

    refused = await authenticated_async_client.post(
        f"/tasks/{task_id}/submit/", {"O1": "", "O1_note": "unsure"}
    )
    task = await wf_engine.store.load_task(task_id)
    assert task.state == TaskState.READY
    assert "This field is required." in refused.content.decode()

    await authenticated_async_client.post(
        f"/tasks/{task_id}/submit/", {"O1": "partial", "O1_note": "lock files unscanned"}
    )

    process = await wf_engine.store.load_process(process_id)
    assert process.state == ProcessState.COMPLETE
    result = process.properties["review_result"]
    assert result["status"] == "ruled"
    assert result["ruling"] == "O1: partial: lock files unscanned"
    assert result["followups"] == ["O1"]
    assert "**partial** (lock files unscanned)" in result["table_markdown"]
