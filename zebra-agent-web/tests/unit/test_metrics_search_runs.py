"""Tests for DjangoMetricsStore.search_runs (F138)."""

from datetime import UTC, datetime

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from zebra_agent_web.api.models import WorkflowRunModel
from zebra_agent_web.metrics_store import DjangoMetricsStore
from zebra_agent_web.middleware import _current_user_id_var

User = get_user_model()


@pytest.fixture
def user_a(db):
    return User.objects.create_user(username="user_a_search", password="x")


@pytest.fixture
def user_b(db):
    return User.objects.create_user(username="user_b_search", password="x")


@sync_to_async
def _seed(user_a, user_b):
    rows = [
        ("r1", "Research", "Compare Pension providers", 1, True, user_a.id),
        ("r3", "Research", "pension tax relief", 3, False, user_a.id),
        ("r5", "Haiku", "write a haiku about autumn", 5, True, user_a.id),
        ("rb", "Research", "pension for user b", 3, True, user_b.id),
    ]
    for run_id, workflow, goal, day, success, uid in rows:
        WorkflowRunModel.objects.create(
            id=run_id,
            workflow_name=workflow,
            goal=goal,
            started_at=datetime(2026, 10, day, 12, tzinfo=UTC),
            success=success,
            user_id=uid,
        )


@pytest.mark.django_db(transaction=True)
async def test_date_window(user_a, user_b):
    await _seed(user_a, user_b)
    runs = await DjangoMetricsStore().search_runs(
        since=datetime(2026, 10, 2, tzinfo=UTC),
        until=datetime(2026, 10, 5, tzinfo=UTC),
        user_id=user_a.id,
    )
    assert [r.id for r in runs] == ["r3"]


@pytest.mark.django_db(transaction=True)
async def test_text_case_insensitive_newest_first(user_a, user_b):
    await _seed(user_a, user_b)
    runs = await DjangoMetricsStore().search_runs(text="PENSION", user_id=user_a.id)
    assert [r.id for r in runs] == ["r3", "r1"]


@pytest.mark.django_db(transaction=True)
async def test_combined_filters(user_a, user_b):
    await _seed(user_a, user_b)
    runs = await DjangoMetricsStore().search_runs(
        text="pension", workflow_name="Research", success=True, user_id=user_a.id
    )
    assert [r.id for r in runs] == ["r1"]


@pytest.mark.django_db(transaction=True)
async def test_current_user_scoping(user_a, user_b):
    await _seed(user_a, user_b)
    token = _current_user_id_var.set(user_a.id)
    try:
        runs = await DjangoMetricsStore().search_runs(text="pension")
    finally:
        _current_user_id_var.reset(token)
    assert "rb" not in {r.id for r in runs}


@pytest.mark.django_db(transaction=True)
async def test_explicit_user_without_request_user(user_a, user_b):
    """The daemon has no request user; an explicit user_id still scopes results."""
    await _seed(user_a, user_b)
    runs = await DjangoMetricsStore().search_runs(user_id=user_b.id)
    assert [r.id for r in runs] == ["rb"]


@pytest.mark.django_db(transaction=True)
async def test_limit_capped(user_a, user_b):
    @sync_to_async
    def _many():
        WorkflowRunModel.objects.bulk_create(
            WorkflowRunModel(
                id=f"m{i}",
                workflow_name="W",
                goal="g",
                started_at=datetime(2026, 10, 1, tzinfo=UTC),
            )
            for i in range(205)
        )

    await _many()
    assert len(await DjangoMetricsStore().search_runs(limit=10000)) == 200


@pytest.mark.django_db(transaction=True)
async def test_text_wildcards_are_literal(user_a, user_b):
    """SQL LIKE wildcards in search text match literally, not as patterns."""
    await _seed(user_a, user_b)

    @sync_to_async
    def _add():
        WorkflowRunModel.objects.create(
            id="pct",
            workflow_name="W",
            goal="grow savings by 100% safely",
            started_at=datetime(2026, 10, 2, tzinfo=UTC),
            user_id=user_a.id,
        )

    await _add()
    store = DjangoMetricsStore()
    assert [r.id for r in await store.search_runs(text="100%", user_id=user_a.id)] == ["pct"]
    assert await store.search_runs(text="%", user_id=user_b.id) == []
    assert await store.search_runs(text="_", user_id=user_a.id) == []
