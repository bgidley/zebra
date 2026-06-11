"""Integration tests for DjangoTrustStore (F12 / REQ-TRUST-001).

Mirrors the InMemoryTrustStore test cases so both backends satisfy the same
contract against a real Django ORM backend.
"""

from __future__ import annotations

import pytest
from zebra_agent.storage.trust import (
    DEFAULT_DOMAINS,
    TrustLevel,
    register_domain,
    reset_domain_registry,
)
from zebra_agent_web.trust_store import DjangoTrustStore


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_domain_registry()
    yield
    reset_domain_registry()


@pytest.fixture
def store() -> DjangoTrustStore:
    return DjangoTrustStore()


@pytest.mark.django_db(transaction=True)
async def test_unset_domain_reads_as_supervised(store: DjangoTrustStore) -> None:
    from zebra_agent_web.api.models import TrustLevelModel

    assert await store.get_trust_level(1, "finance") == TrustLevel.SUPERVISED
    assert TrustLevelModel.objects.count() == 0


@pytest.mark.django_db(transaction=True)
async def test_set_then_read_back(store: DjangoTrustStore) -> None:
    await store.set_trust_level(1, "code", TrustLevel.SEMI_AUTONOMOUS, "20 clean runs", "ben")
    assert await store.get_trust_level(1, "code") == TrustLevel.SEMI_AUTONOMOUS


@pytest.mark.django_db(transaction=True)
async def test_trust_levels_are_user_scoped(store: DjangoTrustStore) -> None:
    await store.set_trust_level(1, "code", TrustLevel.AUTONOMOUS, "earned", "ben")
    assert await store.get_trust_level(2, "code") == TrustLevel.SUPERVISED


@pytest.mark.django_db(transaction=True)
async def test_unknown_domain_rejected_on_write(store: DjangoTrustStore) -> None:
    from zebra_agent_web.api.models import TrustChangeModel, TrustLevelModel

    with pytest.raises(ValueError, match="time-travel"):
        await store.set_trust_level(1, "time-travel", TrustLevel.AUTONOMOUS, "nope", "ben")
    assert TrustLevelModel.objects.count() == 0
    assert TrustChangeModel.objects.count() == 0


@pytest.mark.django_db(transaction=True)
async def test_get_all_trust_levels_merges_defaults(store: DjangoTrustStore) -> None:
    await store.set_trust_level(1, "code", TrustLevel.SEMI_AUTONOMOUS, "earned", "ben")
    levels = await store.get_all_trust_levels(1)
    assert set(levels) == set(DEFAULT_DOMAINS)
    assert levels["code"] == TrustLevel.SEMI_AUTONOMOUS
    assert all(lv == TrustLevel.SUPERVISED for d, lv in levels.items() if d != "code")


@pytest.mark.django_db(transaction=True)
async def test_registered_custom_domain_accepted(store: DjangoTrustStore) -> None:
    register_domain("gardening")
    await store.set_trust_level(1, "gardening", TrustLevel.SEMI_AUTONOMOUS, "trial", "ben")
    levels = await store.get_all_trust_levels(1)
    assert levels["gardening"] == TrustLevel.SEMI_AUTONOMOUS


@pytest.mark.django_db(transaction=True)
async def test_change_writes_audit_record(store: DjangoTrustStore) -> None:
    record = await store.set_trust_level(
        1, "code", TrustLevel.SEMI_AUTONOMOUS, "20 clean runs", "ben"
    )
    assert record.old_level == TrustLevel.SUPERVISED
    assert record.new_level == TrustLevel.SEMI_AUTONOMOUS

    changes = await store.list_trust_changes(1, "code")
    assert len(changes) == 1
    entry = changes[0]
    assert entry.user_id == 1
    assert entry.domain == "code"
    assert entry.old_level == TrustLevel.SUPERVISED
    assert entry.new_level == TrustLevel.SEMI_AUTONOMOUS
    assert entry.reason == "20 clean runs"
    assert entry.changed_by == "ben"
    assert entry.changed_at is not None


@pytest.mark.django_db(transaction=True)
async def test_history_accumulates_and_chains(store: DjangoTrustStore) -> None:
    await store.set_trust_level(1, "code", TrustLevel.SEMI_AUTONOMOUS, "step 1", "ben")
    await store.set_trust_level(1, "code", TrustLevel.AUTONOMOUS, "step 2", "ben")
    await store.set_trust_level(1, "code", TrustLevel.SUPERVISED, "step 3", "ben")

    changes = await store.list_trust_changes(1, "code")
    assert [c.reason for c in changes] == ["step 3", "step 2", "step 1"]
    assert changes[0].old_level == changes[1].new_level
    assert changes[1].old_level == changes[2].new_level
    assert changes[2].old_level == TrustLevel.SUPERVISED


@pytest.mark.django_db(transaction=True)
async def test_list_trust_changes_filters_by_domain_and_user(store: DjangoTrustStore) -> None:
    await store.set_trust_level(1, "code", TrustLevel.SEMI_AUTONOMOUS, "a", "ben")
    await store.set_trust_level(1, "home", TrustLevel.AUTONOMOUS, "b", "ben")
    await store.set_trust_level(2, "code", TrustLevel.AUTONOMOUS, "c", "alice")

    assert [c.reason for c in await store.list_trust_changes(1)] == ["b", "a"]
    assert [c.reason for c in await store.list_trust_changes(1, "code")] == ["a"]
    assert [c.reason for c in await store.list_trust_changes(2)] == ["c"]


@pytest.mark.django_db(transaction=True)
async def test_audit_rows_are_immutable() -> None:
    from zebra_agent_web.api.models import TrustChangeModel

    store = DjangoTrustStore()
    record = await store.set_trust_level(1, "code", TrustLevel.AUTONOMOUS, "earned", "ben")

    row = TrustChangeModel.objects.get(id=record.id)
    row.reason = "tampered"
    with pytest.raises(NotImplementedError):
        row.save()
    with pytest.raises(NotImplementedError):
        row.delete()
