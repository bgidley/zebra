"""A human task parked on an older workflow version keeps its definition (#219).

Processes pin their definition by id, and the id includes the version. Upgrading a
built-in workflow on deploy must not delete the old version's stored definition, or
a ruling parked on *Outcome Review* v3 can no longer be opened or completed once v4
ships (the v3 row was deleted on prod by the #215 deploy).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskInstance, TaskResult, TaskState
from zebra.definitions.loader import load_definition_from_yaml
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_agent.library import WorkflowLibrary
from zebra_agent_web.api import agent_engine
from zebra_agent_web.api import engine as engine_module

V3_YAML = Path(__file__).parent / "fixtures" / "outcome_review_v3.yaml"
V4_YAML = Path(__file__).parents[3] / "zebra-agent" / "workflows" / "outcome_review.yaml"

TABLE = "| O5 | Zebra: met | Claude: partial |"
SUMMARY = "O5 summary row (v4 only)"
ZEBRA_SAID = "Zebra read the diff and judged O5 met"


class StubCompare(TaskAction):
    """Stands in for compare_outcome_reviews: records the ruling, ends the review."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.ok(output={"agreed": True})


@pytest.fixture
def identity(transactional_db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
def wf_engine(monkeypatch):
    from zebra_agent_web.storage import DjangoStore

    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("compare_outcome_reviews", StubCompare)
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


async def _park_v3_ruling(wf_engine: WorkflowEngine) -> tuple[str, str]:
    """A v3 Outcome Review waiting on its human ruling, as the daemon leaves it."""
    v3 = load_definition_from_yaml(V3_YAML.read_text())
    assert v3.version == 3
    await wf_engine.store.save_definition(v3)

    process = await wf_engine.create_process(
        v3,
        properties={
            "issue": 211,
            "title": "Some change",
            "deployed_hash": "abc1234",
            "review_result": {
                "table_markdown": TABLE,
                "summary_markdown": SUMMARY,
                "dispute_notes": "O5: Zebra met, Claude partial",
            },
            "__task_output_zebra_review": {"response": ZEBRA_SAID},
        },
    )
    running = await wf_engine.store.load_process(process.id)
    await wf_engine.store.save_process(running.model_copy(update={"state": ProcessState.RUNNING}))
    task = TaskInstance(
        id="ruling-v3",
        task_definition_id="human_ruling",
        process_id=process.id,
        state=TaskState.READY,
        foe_id="foe-v3",
    )
    await wf_engine.store.save_task(task)
    return process.id, task.id


async def _deploy_v4(tmp_path: Path) -> int:
    """Run the startup step that installs built-ins: library has v3, the build ships v4.

    Runs it twice, as every restart does; the second run changes nothing.
    """
    library_dir, builtin_dir = tmp_path / "library", tmp_path / "builtin"
    library_dir.mkdir()
    builtin_dir.mkdir()
    shutil.copy(V3_YAML, library_dir / "outcome_review.yaml")
    shutil.copy(V4_YAML, builtin_dir / "outcome_review.yaml")
    library = WorkflowLibrary(library_dir)
    copied = await agent_engine.install_builtin_workflows(library, builtin_dir)
    assert await agent_engine.install_builtin_workflows(library, builtin_dir) == 0
    return copied


@pytest.mark.django_db(transaction=True)
async def test_parked_v3_ruling_renders_from_v3_after_v4_ships(
    wf_engine, identity, authenticated_async_client, tmp_path
):
    process_id, task_id = await _park_v3_ruling(wf_engine)
    v4 = load_definition_from_yaml(V4_YAML.read_text())
    assert v4.version == 4
    process = await wf_engine.store.load_process(process_id)
    assert v4.id != process.definition_id

    assert await _deploy_v4(tmp_path) == 1
    # A new run after the deploy stores v4 alongside v3.
    await wf_engine.store.save_definition(v4)

    pinned = await wf_engine.store.load_definition(process.definition_id)
    assert pinned is not None and pinned.version == 3

    response = await authenticated_async_client.get(f"/tasks/{task_id}/")
    content = response.content.decode()
    assert response.status_code == 200
    # v3's comparison field: the side-by-side table, not v4's summary.
    assert "Verdicts side by side" in content
    assert "O5" in content and "Claude: partial" in content
    assert SUMMARY not in content
    # v3 shows earlier steps' outputs; v4 hides them (show_prior_outputs: false).
    assert ZEBRA_SAID in content


@pytest.mark.django_db(transaction=True)
async def test_parked_v3_ruling_completes_after_v4_ships(wf_engine, identity, tmp_path):
    process_id, task_id = await _park_v3_ruling(wf_engine)
    await _deploy_v4(tmp_path)

    await wf_engine.complete_task(task_id, TaskResult.ok(output={"ruling": "O5 partial"}))

    process = await wf_engine.store.load_process(process_id)
    assert process.state == ProcessState.COMPLETE
