"""Tests for manual review of tasks flagged by recovery (#130): views and REST API.

Uses InMemoryStore and a real WorkflowEngine, monkey-patching the engine
singletons (same approach as test_human_tasks.py).
"""

import pytest
from zebra.core.engine import MANUAL_REVIEW_FLAG, WorkflowEngine
from zebra.core.models import (
    ProcessDefinition,
    ProcessState,
    RoutingDefinition,
    TaskDefinition,
    TaskInstance,
    TaskResult,
    TaskState,
)
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_agent_web.api import manual_review

pytestmark = [pytest.mark.django_db(transaction=True)]


class SimulatedCrash(BaseException):
    """Escapes the engine's ``except Exception`` like a real process kill."""


class SideEffectAction(TaskAction):
    crash = True

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        if type(self).crash:
            raise SimulatedCrash()
        return TaskResult.ok(output="sent")


DEFINITION = ProcessDefinition(
    id="send-email",
    name="Send Email",
    first_task_id="send",
    tasks={
        "send": TaskDefinition(id="send", name="Send The Email", action="side_effect"),
        "done": TaskDefinition(id="done", name="Done"),
    },
    routings=[RoutingDefinition(id="r1", source_task_id="send", dest_task_id="done")],
)


class _StubMetricsStore:
    async def get_in_progress_runs(self):
        return []

    async def get_completed_runs(self, limit=20):
        return []

    async def get_recent_runs(self, limit=10):
        return []

    async def get_run(self, run_id):
        return None

    async def get_task_executions(self, run_id):
        return []


class _StubLibrary:
    async def list_workflows(self):
        return []


@pytest.fixture(autouse=True)
def _setup_complete(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def wf_engine(store):
    SideEffectAction.crash = True
    registry = ActionRegistry()
    registry.register_action("side_effect", SideEffectAction)
    return WorkflowEngine(store, registry)


@pytest.fixture(autouse=True)
def patch_engine(store, wf_engine, monkeypatch):
    import zebra_agent_web.api.agent_engine as agent_engine_module
    import zebra_agent_web.api.engine as engine_module

    monkeypatch.setattr(engine_module, "_store", store)
    monkeypatch.setattr(engine_module, "_engine", wf_engine)
    monkeypatch.setattr(agent_engine_module, "_metrics", _StubMetricsStore())
    monkeypatch.setattr(agent_engine_module, "_library", _StubLibrary())


@pytest.fixture
def background(monkeypatch):
    """Record background re-executions instead of spawning threads."""
    calls: list[str] = []
    monkeypatch.setattr(manual_review, "_run_in_background", lambda eng, tid: calls.append(tid))
    return calls


@pytest.fixture
def client(db):
    from django.contrib.auth import get_user_model
    from django.test import AsyncClient

    user = get_user_model().objects.create_user(username="testuser")
    c = AsyncClient()
    c.force_login(user)
    return c


async def _flagged(wf_engine, run_id="run-1", parent_id=None):
    """Create a process whose task was interrupted and flagged by recovery."""
    props = {"goal": "Email the team"}
    if run_id:
        props["run_id"] = run_id
    process = await wf_engine.create_process(
        DEFINITION, properties=props, parent_process_id=parent_id
    )
    with pytest.raises(SimulatedCrash):
        await wf_engine.start_process(process.id)
    await wf_engine.resume_all_processes()
    [task] = await wf_engine.store.get_running_tasks(process.id)
    assert task.properties[MANUAL_REVIEW_FLAG] is True
    return process, task


# ---------------------------------------------------------------------------
# find_review_tasks
# ---------------------------------------------------------------------------


async def test_find_review_tasks_resolves_run_from_parent(wf_engine, store):
    parent, parent_task = await _flagged(wf_engine, run_id="run-7")
    child, child_task = await _flagged(wf_engine, run_id=None, parent_id=parent.id)

    tasks = await manual_review.find_review_tasks(store, run_id="run-7")

    assert {t["id"] for t in tasks} == {parent_task.id, child_task.id}
    assert all(t["task_name"] == "Send The Email" for t in tasks)
    assert await manual_review.find_review_tasks(store, run_id="other") == []


# ---------------------------------------------------------------------------
# Web views
# ---------------------------------------------------------------------------


async def test_activity_shows_review_controls(client, wf_engine):
    _, task = await _flagged(wf_engine)

    response = await client.get("/activity/")

    html = response.content.decode()
    assert response.status_code == 200
    assert "review needed" in html
    assert "Needs manual review" in html
    assert f"/tasks/{task.id}/retry/" in html
    assert f"/tasks/{task.id}/fail/" in html


async def test_run_detail_shows_review_controls(client, wf_engine):
    _, task = await _flagged(wf_engine, run_id="run-9")

    response = await client.get("/runs/run-9/")

    html = response.content.decode()
    assert response.status_code == 200
    assert "Needs manual review" in html
    assert f"/tasks/{task.id}/retry/" in html


async def test_retry_view_resets_task_and_schedules_rerun(client, wf_engine, background):
    process, task = await _flagged(wf_engine)

    response = await client.post(f"/tasks/{task.id}/retry/", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "Retrying" in response.content.decode()
    reset = await wf_engine.store.load_task(task.id)
    assert reset.state == TaskState.READY
    assert MANUAL_REVIEW_FLAG not in reset.properties
    assert background == [task.id]

    # What the background worker does: re-run the task to completion
    SideEffectAction.crash = False
    await wf_engine.transition_task(task.id)
    assert (await wf_engine.store.load_process(process.id)).state == ProcessState.COMPLETE


async def test_retry_view_rejects_unflagged_task(client, wf_engine, background):
    _, task = await _flagged(wf_engine)
    await wf_engine.retry_task(task.id, execute=False)

    response = await client.post(f"/tasks/{task.id}/retry/", headers={"HX-Request": "true"})

    assert response.status_code == 409
    assert background == []


async def test_fail_view_fails_process_and_ancestors(client, wf_engine):
    parent, _ = await _flagged(wf_engine, run_id="run-3")
    child, child_task = await _flagged(wf_engine, run_id=None, parent_id=parent.id)

    response = await client.post(f"/tasks/{child_task.id}/fail/", headers={"HX-Request": "true"})

    assert response.status_code == 200
    for pid in (child.id, parent.id):
        process = await wf_engine.store.load_process(pid)
        assert process.state == ProcessState.FAILED
        assert "manual review" in process.properties["__error__"]


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------


async def test_api_lists_review_tasks(client, wf_engine):
    _, task = await _flagged(wf_engine, run_id="run-5")

    response = await client.get("/api/review-tasks/?run_id=run-5")

    assert response.status_code == 200
    [item] = response.json()
    assert item["id"] == task.id
    assert item["run_id"] == "run-5"
    assert item["execution_attempt"] == 1


async def test_api_retry(client, wf_engine, background):
    _, task = await _flagged(wf_engine)

    response = await client.post(f"/api/tasks/{task.id}/retry/")

    assert response.status_code == 202
    assert response.json() == {"retrying": True, "task_id": task.id, "state": "ready"}
    assert background == [task.id]


async def test_api_retry_unknown_task_404(client, background):
    response = await client.post("/api/tasks/nope/retry/")

    assert response.status_code == 404


async def test_api_fail_with_reason(client, wf_engine):
    process, task = await _flagged(wf_engine)

    response = await client.post(
        f"/api/tasks/{task.id}/fail/",
        data={"reason": "Email already sent"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["failed_process_ids"] == [process.id]
    failed = await wf_engine.store.load_process(process.id)
    assert failed.state == ProcessState.FAILED
    assert failed.properties["__error__"] == "Email already sent"


async def test_api_fail_rejects_unflagged_task(client, wf_engine):
    _, task = await _flagged(wf_engine)
    await wf_engine.retry_task(task.id, execute=False)

    response = await client.post(f"/api/tasks/{task.id}/fail/")

    assert response.status_code == 409


async def test_api_requires_authentication(wf_engine, background):
    from django.test import AsyncClient

    _, task = await _flagged(wf_engine)

    response = await AsyncClient().post(f"/api/tasks/{task.id}/retry/")

    assert response.status_code in (401, 403)
    assert background == []


def test_recovery_cap_setting_default():
    from django.conf import settings

    assert settings.ZEBRA_AGENT_SETTINGS["RECOVERY_MAX_INTERRUPTED_ATTEMPTS"] == 3
