"""Web-view test for F22 dilemma escalation — the resolution UI shows both sides.

Acceptance for #22: a triggered dilemma produces a pause (human task) whose form
presents both sides of the conflict and a proceed/decline decision.
"""

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessDefinition, TaskDefinition
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry

pytestmark = [pytest.mark.django_db(transaction=True)]


def _dilemma_resolution_definition() -> ProcessDefinition:
    """A one-task workflow mirroring the agent loop's ethics_dilemma_resolution task."""
    return ProcessDefinition(
        id="dilemma-wf",
        name="Dilemma Resolution Test",
        version=1,
        first_task_id="ethics_dilemma_resolution",
        tasks={
            "ethics_dilemma_resolution": TaskDefinition(
                id="ethics_dilemma_resolution",
                name="Resolve Ethics Dilemma",
                auto=False,
                properties={
                    "schema": {
                        "type": "object",
                        "title": "Ethics Dilemma — Your Decision Needed",
                        "required": ["decision"],
                        "properties": {
                            "dilemma": {
                                "type": "string",
                                "title": "The Dilemma (both sides)",
                                "format": "multiline",
                                "default": "{{dilemma_display}}",
                                "readOnly": True,
                            },
                            "decision": {
                                "type": "string",
                                "title": "Your decision",
                                "enum": ["proceed", "decline"],
                                "default": "proceed",
                            },
                        },
                    }
                },
            ),
        },
        routings=[],
    )


@pytest.fixture(autouse=True)
def _ensure_setup_complete(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def wf_engine(store):
    return WorkflowEngine(store, ActionRegistry())


@pytest.fixture(autouse=True)
def patch_engine(store, wf_engine):
    import zebra_agent_web.api.engine as engine_module

    saved = (engine_module._store, engine_module._engine)
    engine_module._store = store
    engine_module._engine = wf_engine
    yield
    engine_module._store, engine_module._engine = saved


@pytest.fixture
def client(db):
    from django.contrib.auth import get_user_model
    from django.test import AsyncClient

    User = get_user_model()
    user = User.objects.create_user(username="testuser")
    c = AsyncClient()
    c.force_login(user)
    return c


class TestDilemmaResolutionUI:
    async def test_resolution_form_shows_both_sides_and_decision(self, client, wf_engine, store):
        defn = _dilemma_resolution_definition()
        process = await wf_engine.create_process(defn)
        await wf_engine.start_process(process.id)

        # Seed the dilemma rendering the gate would have produced
        dilemma_display = (
            "Trade-off: honesty vs kindness\n"
            "• PROCEED (values: honesty): candid feedback respects them\n"
            "• DECLINE (values: kindness): blunt feedback may wound\n"
            "Agent recommendation: proceed — you prize honesty"
        )
        running = await store.load_process(process.id)
        updated = running.model_copy(update={"properties": {"dilemma_display": dilemma_display}})
        await store.save_process(updated)

        pending = await wf_engine.get_pending_tasks(process.id)
        task = pending[0]
        assert task.task_definition_id == "ethics_dilemma_resolution"

        response = await client.get(f"/tasks/{task.id}/")
        assert response.status_code == 200
        content = response.content.decode()
        # Both sides of the dilemma are rendered for the human
        assert "honesty vs kindness" in content
        assert "PROCEED" in content and "DECLINE" in content
        assert "Agent recommendation" in content
        # The decision control offers proceed and decline
        assert 'value="proceed"' in content
        assert 'value="decline"' in content
