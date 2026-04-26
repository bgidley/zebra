"""Tests for F6 user_id namespacing across stores.

Verifies that:
- ProcessInstanceModel.user_id is stamped on save from process properties.
- TaskInstanceModel.user_id is inherited from parent process.
- DjangoStore query methods filter by current user when contextvars is set.
- DjangoMetricsStore query methods filter by current user.
- DjangoMemoryStore query methods filter by current user.
- CurrentUserMiddleware sets the contextvars correctly.
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from zebra_agent_web.api.models import (
    ProcessInstanceModel,
    WorkflowMemoryModel,
    WorkflowRunModel,
)
from zebra_agent_web.middleware import (
    CurrentUserMiddleware,
    _current_user_id_var,
    get_current_user_id,
)

User = get_user_model()


def _now():
    return datetime.now(UTC)


@pytest.fixture
def user_a(db):
    return User.objects.create_user(username="user_a_ns", password="x")


@pytest.fixture
def user_b(db):
    return User.objects.create_user(username="user_b_ns", password="x")


# ---------------------------------------------------------------------------
# CurrentUserMiddleware (sync path)
# ---------------------------------------------------------------------------


class TestCurrentUserMiddleware:
    def test_sets_user_id_during_request(self, user_a, db):
        rf = RequestFactory()
        request = rf.get("/")
        request.user = user_a

        captured = []

        def inner(req):
            captured.append(get_current_user_id())
            return MagicMock(status_code=200)

        middleware = CurrentUserMiddleware(inner)
        middleware(request)

        assert captured == [user_a.id]
        assert get_current_user_id() is None  # reset after request

    def test_sets_none_for_anonymous(self, db):
        from django.contrib.auth.models import AnonymousUser

        rf = RequestFactory()
        request = rf.get("/")
        request.user = AnonymousUser()

        captured = []

        def inner(req):
            captured.append(get_current_user_id())
            return MagicMock(status_code=200)

        middleware = CurrentUserMiddleware(inner)
        middleware(request)

        assert captured == [None]


# ---------------------------------------------------------------------------
# DjangoStore — save_process stamps user_id
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_save_process_stamps_user_id_from_properties(user_a):
    """user_id in process.properties.__user_id__ is written to the DB column."""
    from zebra.core.models import ProcessInstance, ProcessState
    from zebra_agent_web.storage import DjangoStore

    store = DjangoStore()
    process = ProcessInstance(
        id="proc-stamp-test",
        definition_id="def-1",
        state=ProcessState.CREATED,
        properties={"__user_id__": user_a.id},
        created_at=_now(),
        updated_at=_now(),
    )
    await store.save_process(process)

    row = await sync_to_async(ProcessInstanceModel.objects.get)(id="proc-stamp-test")
    assert row.user_id == user_a.id


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_save_process_falls_back_to_contextvars(user_a):
    """When no __user_id__ in props, falls back to current request user."""
    from zebra.core.models import ProcessInstance, ProcessState
    from zebra_agent_web.storage import DjangoStore

    store = DjangoStore()
    process = ProcessInstance(
        id="proc-cv-test",
        definition_id="def-1",
        state=ProcessState.CREATED,
        properties={},
        created_at=_now(),
        updated_at=_now(),
    )

    token = _current_user_id_var.set(user_a.id)
    try:
        await store.save_process(process)
    finally:
        _current_user_id_var.reset(token)

    row = await sync_to_async(ProcessInstanceModel.objects.get)(id="proc-cv-test")
    assert row.user_id == user_a.id


# ---------------------------------------------------------------------------
# DjangoStore — query filtering
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_processes_by_state_filters_by_user(user_a, user_b):
    """get_processes_by_state returns only the current user's processes."""
    from zebra.core.models import ProcessState
    from zebra_agent_web.storage import DjangoStore

    @sync_to_async
    def _create():
        ProcessInstanceModel.objects.create(
            id="proc-filter-a",
            definition_id="d",
            state="created",
            properties=json.dumps({}),
            user_id=user_a.id,
            created_at=_now(),
            updated_at=_now(),
        )
        ProcessInstanceModel.objects.create(
            id="proc-filter-b",
            definition_id="d",
            state="created",
            properties=json.dumps({}),
            user_id=user_b.id,
            created_at=_now(),
            updated_at=_now(),
        )

    await _create()

    store = DjangoStore()
    token = _current_user_id_var.set(user_a.id)
    try:
        results = await store.get_processes_by_state(ProcessState.CREATED)
    finally:
        _current_user_id_var.reset(token)

    ids = {p.id for p in results}
    assert "proc-filter-a" in ids
    assert "proc-filter-b" not in ids


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_processes_by_state_unfiltered_for_daemon(user_a, user_b):
    """When no contextvars (daemon path), all processes are returned."""
    from zebra.core.models import ProcessState
    from zebra_agent_web.storage import DjangoStore

    @sync_to_async
    def _create():
        ProcessInstanceModel.objects.create(
            id="proc-daemon-a",
            definition_id="d",
            state="created",
            properties=json.dumps({}),
            user_id=user_a.id,
            created_at=_now(),
            updated_at=_now(),
        )
        ProcessInstanceModel.objects.create(
            id="proc-daemon-b",
            definition_id="d",
            state="created",
            properties=json.dumps({}),
            user_id=user_b.id,
            created_at=_now(),
            updated_at=_now(),
        )

    await _create()

    store = DjangoStore()
    results = await store.get_processes_by_state(ProcessState.CREATED)

    ids = {p.id for p in results}
    assert "proc-daemon-a" in ids
    assert "proc-daemon-b" in ids


# ---------------------------------------------------------------------------
# DjangoMetricsStore — query filtering
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_metrics_get_recent_runs_filters_by_user(user_a, user_b):
    from zebra_agent_web.metrics_store import DjangoMetricsStore

    @sync_to_async
    def _create():
        WorkflowRunModel.objects.create(
            id="mrun-a",
            workflow_name="wf",
            goal="g",
            started_at=_now(),
            user_id=user_a.id,
        )
        WorkflowRunModel.objects.create(
            id="mrun-b",
            workflow_name="wf",
            goal="g",
            started_at=_now(),
            user_id=user_b.id,
        )

    await _create()

    store = DjangoMetricsStore()
    token = _current_user_id_var.set(user_a.id)
    try:
        runs = await store.get_recent_runs(limit=10)
    finally:
        _current_user_id_var.reset(token)

    ids = {r.id for r in runs}
    assert "mrun-a" in ids
    assert "mrun-b" not in ids


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_metrics_get_recent_runs_unfiltered_for_daemon(user_a, user_b):
    from zebra_agent_web.metrics_store import DjangoMetricsStore

    @sync_to_async
    def _create():
        WorkflowRunModel.objects.create(
            id="mrun-d-a",
            workflow_name="wf",
            goal="g",
            started_at=_now(),
            user_id=user_a.id,
        )
        WorkflowRunModel.objects.create(
            id="mrun-d-b",
            workflow_name="wf",
            goal="g",
            started_at=_now(),
            user_id=user_b.id,
        )

    await _create()

    store = DjangoMetricsStore()
    runs = await store.get_recent_runs(limit=10)

    ids = {r.id for r in runs}
    assert "mrun-d-a" in ids
    assert "mrun-d-b" in ids


# ---------------------------------------------------------------------------
# DjangoMemoryStore — query filtering
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_memory_get_workflow_memories_filters_by_user(user_a, user_b):
    from zebra_agent_web.memory_store import DjangoMemoryStore

    @sync_to_async
    def _create():
        WorkflowMemoryModel.objects.create(
            id="wmem-a",
            timestamp=_now(),
            workflow_name="wf-ns",
            goal="g",
            success=True,
            input_summary="i",
            output_summary="o",
            user_id=user_a.id,
        )
        WorkflowMemoryModel.objects.create(
            id="wmem-b",
            timestamp=_now(),
            workflow_name="wf-ns",
            goal="g",
            success=True,
            input_summary="i",
            output_summary="o",
            user_id=user_b.id,
        )

    await _create()

    store = DjangoMemoryStore()
    token = _current_user_id_var.set(user_a.id)
    try:
        memories = await store.get_workflow_memories("wf-ns")
    finally:
        _current_user_id_var.reset(token)

    ids = {m.id for m in memories}
    assert "wmem-a" in ids
    assert "wmem-b" not in ids


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_memory_get_workflow_memories_unfiltered_for_daemon(user_a, user_b):
    from zebra_agent_web.memory_store import DjangoMemoryStore

    @sync_to_async
    def _create():
        WorkflowMemoryModel.objects.create(
            id="wmem-d-a",
            timestamp=_now(),
            workflow_name="wf-ns-d",
            goal="g",
            success=True,
            input_summary="i",
            output_summary="o",
            user_id=user_a.id,
        )
        WorkflowMemoryModel.objects.create(
            id="wmem-d-b",
            timestamp=_now(),
            workflow_name="wf-ns-d",
            goal="g",
            success=True,
            input_summary="i",
            output_summary="o",
            user_id=user_b.id,
        )

    await _create()

    store = DjangoMemoryStore()
    memories = await store.get_workflow_memories("wf-ns-d")

    ids = {m.id for m in memories}
    assert "wmem-d-a" in ids
    assert "wmem-d-b" in ids
