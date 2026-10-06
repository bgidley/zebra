"""Web-view tests for ethics outcome surfacing in run pages (#143).

A rejected goal shows which gate rejected it and why; a completed goal shows the
post-execution ethics review with its concerns and recommendations.
"""

from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessInstance, ProcessState
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_agent_web.api.web_views import _extract_ethics_outcome

pytestmark = [pytest.mark.django_db(transaction=True)]

_AGENT_MAIN_LOOP = (
    Path(__file__).resolve().parents[3] / "zebra-agent" / "workflows" / "agent_main_loop.yaml"
)


class _StubMetricsStore:
    """Metrics store with no record for the run — forces the pending fallback path."""

    async def get_run(self, run_id):
        return None

    async def get_task_executions(self, run_id):
        return []


class _Library:
    def __init__(self, definition):
        self._definition = definition

    def get_workflow(self, name):
        if name == self._definition.name:
            return self._definition
        raise ValueError(name)


@pytest.fixture(autouse=True)
def _ensure_setup_complete(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture(autouse=True)
def patch_engine(store):
    import zebra_agent_web.api.agent_engine as agent_engine_module
    import zebra_agent_web.api.engine as engine_module

    saved = (
        engine_module._store,
        engine_module._engine,
        agent_engine_module._metrics,
        agent_engine_module._library,
    )
    engine_module._store = store
    engine_module._engine = WorkflowEngine(store, ActionRegistry())
    agent_engine_module._metrics = _StubMetricsStore()
    agent_engine_module._library = _Library(load_definition_from_yaml(_AGENT_MAIN_LOOP.read_text()))
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

    user = get_user_model().objects.create_user(username="testuser")
    c = AsyncClient()
    c.force_login(user)
    return c


async def _seed(store, run_id, **props):
    await store.save_process(
        ProcessInstance(
            id=f"proc-{run_id}",
            definition_id="Agent Main Loop",
            state=ProcessState.COMPLETE,
            parent_process_id=None,
            properties={"run_id": run_id, "goal": "Some goal", **props},
        )
    )


_REJECTION = {
    "gate": "plan_review",
    "reasoning": "Plan exploits third parties",
    "concerns": ["Treats people merely as means"],
}

_REVIEW = {
    "ethical": False,
    "overall_reasoning": "Output disclosed personal data",
    "concerns": ["Privacy breach"],
    "recommendations": ["Redact personal data"],
}


class TestExtractEthicsOutcome:
    def test_rejection_wins(self):
        props = {"ethics_rejection": _REJECTION, "ethics_post_assessment": _REVIEW}
        assert _extract_ethics_outcome(props) == {"rejection": _REJECTION}

    def test_review(self):
        assert _extract_ethics_outcome({"ethics_post_assessment": _REVIEW}) == {"review": _REVIEW}

    def test_unrecorded_raw_review_is_ignored(self):
        # Raw llm_call text before record_ethics_review normalised it
        assert _extract_ethics_outcome({"ethics_post_assessment": "raw text"}) is None

    def test_nothing(self):
        assert _extract_ethics_outcome({}) is None


class TestEthicsOutcomeInRunPage:
    async def test_rejection_shows_gate_and_reason(self, client, store):
        await _seed(store, "run-rejected", ethics_rejection=_REJECTION)

        response = await client.get("/runs/run-rejected/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "Rejected on Ethical Grounds" in body
        assert "gate: plan_review" in body
        assert "Plan exploits third parties" in body
        assert "Treats people merely as means" in body
        # Error banner carries the reason instead of a generic failure
        assert "Rejected by ethics plan_review" in body

    async def test_post_review_shows_concerns_and_recommendations(self, client, store):
        await _seed(store, "run-reviewed", ethics_post_assessment=_REVIEW)

        response = await client.get("/runs/run-reviewed/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "Post-Execution Ethics Review" in body
        assert "Output disclosed personal data" in body
        assert "Privacy breach" in body
        assert "Redact personal data" in body

    async def test_no_panel_without_outcome(self, client, store):
        await _seed(store, "run-plain")

        response = await client.get("/runs/run-plain/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "Rejected on Ethical Grounds" not in body
        assert "Post-Execution Ethics Review" not in body
