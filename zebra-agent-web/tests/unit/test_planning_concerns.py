"""Web-view tests for F21 proactive concern flagging surfaced in run detail.

Acceptance test for #21: a run whose Agent Main Loop process flagged a planning
concern shows that concern on the run-detail page.
"""

from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessInstance, ProcessState
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry

pytestmark = [pytest.mark.django_db(transaction=True)]

_AGENT_MAIN_LOOP = (
    Path(__file__).resolve().parents[3] / "zebra-agent" / "workflows" / "agent_main_loop.yaml"
)


@pytest.fixture
def agent_main_loop_def():
    return load_definition_from_yaml(_AGENT_MAIN_LOOP.read_text())


class _StubMetricsStore:
    """Metrics store with no record for the run — forces the pending fallback path."""

    async def get_run(self, run_id):
        return None

    async def get_task_executions(self, run_id):
        return []


class _RealishLibrary:
    """Library that returns the real Agent Main Loop definition by name."""

    def __init__(self, definition):
        self._definition = definition

    def get_workflow(self, name):
        if name == self._definition.name:
            return self._definition
        raise ValueError(name)


@pytest.fixture(autouse=True)
def _ensure_setup_complete(db):
    """Mark first-run setup complete so SetupRequiredMiddleware doesn't redirect."""
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def wf_engine(store):
    return WorkflowEngine(store, ActionRegistry())


@pytest.fixture(autouse=True)
def patch_engine(store, wf_engine, agent_main_loop_def):
    import zebra_agent_web.api.agent_engine as agent_engine_module
    import zebra_agent_web.api.engine as engine_module

    saved = (
        engine_module._store,
        engine_module._engine,
        agent_engine_module._metrics,
        agent_engine_module._library,
    )
    engine_module._store = store
    engine_module._engine = wf_engine
    agent_engine_module._metrics = _StubMetricsStore()
    agent_engine_module._library = _RealishLibrary(agent_main_loop_def)

    yield

    (
        engine_module._store,
        engine_module._engine,
        agent_engine_module._metrics,
        agent_engine_module._library,
    ) = saved


@pytest.fixture
def client(db):
    from django.contrib.auth import get_user_model
    from django.test import AsyncClient

    User = get_user_model()
    user = User.objects.create_user(username="testuser")
    c = AsyncClient()
    c.force_login(user)
    return c


async def _seed_parent_process(store, run_id, concerns_output):
    """Seed a COMPLETE Agent Main Loop root process carrying flagged concerns."""
    process = ProcessInstance(
        id=f"proc-{run_id}",
        definition_id="Agent Main Loop",
        state=ProcessState.COMPLETE,
        parent_process_id=None,
        properties={
            "run_id": run_id,
            "goal": "Clean up my downloads folder",
            "workflow_name": "File Operations",
            "planning_concerns": concerns_output,
            "__task_output_flag_concerns": concerns_output,
        },
    )
    await store.save_process(process)
    return process


class TestPlanningConcernsInRunDetail:
    async def test_concern_entry_appears_in_run_detail(self, client, store):
        run_id = "run-with-concern"
        concerns = {
            "concerns": [
                {
                    "description": "Deletes files irreversibly without confirmation",
                    "severity": "high",
                    "step": "execute",
                }
            ],
            "summary": "One high-severity concern flagged.",
        }
        await _seed_parent_process(store, run_id, concerns)

        response = await client.get(f"/runs/{run_id}/")

        assert response.status_code == 200
        body = response.content.decode()
        # "flagged before execution" only appears inside the rendered panel
        # (the panel heading also sits behind an HTML comment, so assert on body text).
        assert "flagged before execution" in body
        assert "Deletes files irreversibly without confirmation" in body
        assert "High" in body

    async def test_no_panel_when_no_concerns(self, client, store):
        run_id = "run-without-concern"
        await _seed_parent_process(store, run_id, {"concerns": [], "summary": "Routine, low risk."})

        response = await client.get(f"/runs/{run_id}/")

        assert response.status_code == 200
        assert "flagged before execution" not in response.content.decode()
