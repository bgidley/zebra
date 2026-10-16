"""Postmortem journal (#175): Django store, /journal/ page and the daemon's timeout hook."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import (
    ProcessDefinition,
    ProcessState,
    TaskDefinition,
    TaskInstance,
    TaskResult,
)
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_agent.memory import PostmortemEntry
from zebra_agent.scheduler import GoalScheduler
from zebra_agent.scheduler.goal_tracker import GoalTracker
from zebra_agent_web.api.daemon import _tick
from zebra_agent_web.api.models import PostmortemModel
from zebra_agent_web.memory_store import DjangoMemoryStore
from zebra_agent_web.middleware import _current_user_id_var

T0 = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


def _entry(**overrides) -> PostmortemEntry:
    fields = {
        "run_id": "run-1",
        "goal": "Summarise news from example.com",
        "workflow_name": "Read Web Page",
        "trigger": "failure",
        "what_happened": "The fetch was blocked.",
        "root_cause": "The site blocks bots.",
        "lesson": "Use the Kagi extract tool for news sites.",
        "voice": "I kept hitting a bot wall; Kagi gets through.",
        "confidence": 0.8,
    }
    fields.update(overrides)
    return PostmortemEntry.create(**fields)


@pytest.mark.django_db(transaction=True)
class TestDjangoPostmortemStore:
    async def test_round_trip_and_user_scope(self):
        store = DjangoMemoryStore()
        await store.add_postmortem(_entry(user_id=1))
        await store.add_postmortem(_entry(run_id="run-2", goal="Other user's goal", user_id=2))

        token = _current_user_id_var.set(1)
        try:
            recent = await store.get_recent_postmortems()
        finally:
            _current_user_id_var.reset(token)

        assert [e.run_id for e in recent] == ["run-1"]
        stored = recent[0]
        assert stored.lesson == "Use the Kagi extract tool for news sites."
        assert stored.voice.startswith("I kept hitting")
        assert stored.confidence == 0.8
        assert stored.user_id == 1
        assert (await store.get_postmortem_by_run_id("run-2")).goal == "Other user's goal"
        assert await store.get_postmortem_by_run_id("missing") is None

    async def test_second_postmortem_for_a_run_is_ignored(self):
        """Racing triggers (daemon timeout + low rating) keep one postmortem per run."""
        store = DjangoMemoryStore()
        await store.add_postmortem(_entry(lesson="first"))
        await store.add_postmortem(_entry(lesson="second"))

        assert await PostmortemModel.objects.filter(run_id="run-1").acount() == 1
        assert (await store.get_postmortem_by_run_id("run-1")).lesson == "first"

    async def test_search_falls_back_to_keywords_off_oracle(self):
        store = DjangoMemoryStore()
        await store.add_postmortem(_entry())
        await store.add_postmortem(_entry(run_id="run-2", goal="Plan a pension", lesson="Ask"))

        found = await store.search_postmortems("Summarise the news", limit=3)

        assert [e.run_id for e in found] == ["run-1"]


@pytest.fixture
def completed_setup(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


def _row(user_id: int | None, **overrides) -> None:
    fields = {
        "id": overrides.pop("id", "pm-1"),
        "user_id": user_id,
        "timestamp": T0,
        "run_id": "run-1",
        "goal": "Summarise news from example.com",
        "workflow_name": "Read Web Page",
        "trigger": "failure",
        "what_happened": "The fetch was blocked.",
        "root_cause": "The site blocks bots.",
        "lesson": "Use the Kagi extract tool for news sites.",
        "voice": "I kept hitting a bot wall; Kagi gets through.",
        "confidence": 0.8,
    }
    fields.update(overrides)
    PostmortemModel.objects.create(**fields)


@pytest.mark.django_db(transaction=True)
def test_journal_lists_the_users_lessons(authenticated_client, test_user, completed_setup):
    _row(test_user.pk)
    _row(
        test_user.pk,
        id="pm-2",
        run_id="",
        trigger="timeout",
        voice=None,
        lesson="Cap web searches at one query.",
        timestamp=T0 + timedelta(hours=1),
    )
    _row(test_user.pk + 1, id="pm-3", run_id="run-3", lesson="Someone else's lesson")

    response = authenticated_client.get("/journal/")

    assert response.status_code == 200
    html = response.content.decode()
    # Newest first; a postmortem without a voice line leads with its lesson
    assert html.index("Cap web searches at one query.") < html.index("I kept hitting a bot wall")
    assert "Use the Kagi extract tool for news sites." in html
    assert "The site blocks bots." in html
    assert 'href="/runs/run-1/"' in html
    assert "After a timed-out run" in html
    assert "Someone else" not in html


@pytest.mark.django_db(transaction=True)
def test_journal_escapes_llm_text(authenticated_client, test_user, completed_setup):
    _row(test_user.pk, lesson="<script>alert(1)</script>", voice="<b>bold</b>")

    html = authenticated_client.get("/journal/").content.decode()

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;bold&lt;/b&gt;" in html


@pytest.mark.django_db(transaction=True)
def test_journal_empty_state(authenticated_client, completed_setup):
    response = authenticated_client.get("/journal/")

    assert response.status_code == 200
    assert "Nothing in my journal yet." in response.content.decode()


class _SlowAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        await asyncio.sleep(30)
        return TaskResult.ok(output="too late")


async def test_daemon_starts_a_postmortem_for_a_timed_out_goal():
    registry = ActionRegistry()
    registry.register_action("slow", _SlowAction)
    engine = WorkflowEngine(InMemoryStore(), registry)
    definition = ProcessDefinition(
        id="slow-goal",
        name="Slow Goal",
        first_task_id="work",
        tasks={"work": TaskDefinition(id="work", name="Work", action="slow")},
        routings=[],
    )
    process = await engine.create_process(definition, properties={"goal": "go", "run_id": "r1"})
    budget_manager = AsyncMock()
    budget_manager.get_status = AsyncMock(
        return_value={"available": 10.0, "spent_today": 0.0, "paced_allowance": 50.0}
    )
    library = MagicMock()

    with (
        patch("zebra_agent_web.api.kill_switch.is_halted", new=AsyncMock(return_value=False)),
        patch("zebra_agent.postmortem.postmortem_failed_goal", new=AsyncMock()) as postmortem,
    ):
        await _tick(
            scheduler=GoalScheduler(engine.store),
            budget_manager=budget_manager,
            engine=engine,
            dry_run=False,
            tracker=GoalTracker(engine, goal_timeout=0.2),
            poll_interval=0.01,
            library=library,
        )

    postmortem.assert_awaited_once()
    called_engine, called_library, finished = postmortem.await_args.args
    assert (called_engine, called_library) == (engine, library)
    assert finished.id == process.id
    assert finished.state == ProcessState.FAILED
