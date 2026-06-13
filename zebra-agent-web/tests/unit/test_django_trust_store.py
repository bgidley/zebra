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


@pytest.mark.django_db(transaction=True)
async def test_add_suggestion_is_pending_and_changes_nothing(store: DjangoTrustStore) -> None:
    suggestion = await store.add_suggestion(1, "code", TrustLevel.SEMI_AUTONOMOUS, "20 runs")

    assert suggestion.status == "pending"
    assert await store.get_trust_level(1, "code") == TrustLevel.SUPERVISED
    assert await store.list_trust_changes(1) == []


@pytest.mark.django_db(transaction=True)
async def test_add_suggestion_validates_domain_and_level(store: DjangoTrustStore) -> None:
    with pytest.raises(ValueError, match="time-travel"):
        await store.add_suggestion(1, "time-travel", TrustLevel.AUTONOMOUS, "x")
    with pytest.raises(ValueError):
        await store.add_suggestion(1, "code", "OMNIPOTENT", "x")
    assert await store.list_suggestions(1) == []


@pytest.mark.django_db(transaction=True)
async def test_list_suggestions_filters_by_user_and_status(store: DjangoTrustStore) -> None:
    s1 = await store.add_suggestion(1, "code", TrustLevel.SEMI_AUTONOMOUS, "a")
    await store.add_suggestion(1, "home", TrustLevel.AUTONOMOUS, "b")
    await store.add_suggestion(2, "code", TrustLevel.AUTONOMOUS, "c")
    await store.resolve_suggestion(s1.id, approve=False, resolved_by="ben")

    assert len(await store.list_suggestions(1)) == 2
    pending = await store.list_suggestions(1, status="pending")
    assert [s.evidence for s in pending] == ["b"]
    assert [s.evidence for s in await store.list_suggestions(2)] == ["c"]


@pytest.mark.django_db(transaction=True)
async def test_approve_changes_level_and_audits_resolver(store: DjangoTrustStore) -> None:
    suggestion = await store.add_suggestion(1, "code", TrustLevel.SEMI_AUTONOMOUS, "20 runs")

    resolved = await store.resolve_suggestion(suggestion.id, approve=True, resolved_by="ben")

    assert resolved.status == "approved"
    assert resolved.resolved_by == "ben"
    assert resolved.resolved_at is not None
    assert await store.get_trust_level(1, "code") == TrustLevel.SEMI_AUTONOMOUS
    changes = await store.list_trust_changes(1, "code")
    assert len(changes) == 1
    assert changes[0].changed_by == "ben"
    assert "20 runs" in changes[0].reason


@pytest.mark.django_db(transaction=True)
async def test_reject_leaves_level_untouched(store: DjangoTrustStore) -> None:
    suggestion = await store.add_suggestion(1, "code", TrustLevel.AUTONOMOUS, "trust me")

    resolved = await store.resolve_suggestion(suggestion.id, approve=False, resolved_by="ben")

    assert resolved.status == "rejected"
    assert await store.get_trust_level(1, "code") == TrustLevel.SUPERVISED
    assert await store.list_trust_changes(1) == []


@pytest.mark.django_db(transaction=True)
async def test_double_resolution_rejected(store: DjangoTrustStore) -> None:
    suggestion = await store.add_suggestion(1, "code", TrustLevel.AUTONOMOUS, "x")
    await store.resolve_suggestion(suggestion.id, approve=False, resolved_by="ben")

    with pytest.raises(ValueError, match="already"):
        await store.resolve_suggestion(suggestion.id, approve=True, resolved_by="ben")
    assert await store.get_trust_level(1, "code") == TrustLevel.SUPERVISED


@pytest.mark.django_db(transaction=True)
async def test_unknown_suggestion_rejected(store: DjangoTrustStore) -> None:
    with pytest.raises(ValueError, match="Unknown"):
        await store.resolve_suggestion("nope", approve=True, resolved_by="ben")


@pytest.mark.django_db(transaction=True)
async def test_pause_all_reverts_elevated_and_audits(store: DjangoTrustStore) -> None:
    await store.set_trust_level(1, "code", TrustLevel.AUTONOMOUS, "earned", "ben")
    await store.set_trust_level(1, "scheduling", TrustLevel.SEMI_AUTONOMOUS, "ok", "ben")

    reverted = await store.pause_all(1, "stop everything", "ben")

    assert set(reverted) == {"code", "scheduling"}
    assert await store.get_trust_level(1, "code") == TrustLevel.SUPERVISED
    assert await store.get_trust_level(1, "scheduling") == TrustLevel.SUPERVISED
    latest = (await store.list_trust_changes(1, "code"))[0]
    assert latest.new_level == TrustLevel.SUPERVISED
    assert latest.changed_by == "ben"
    assert "Emergency override" in latest.reason


@pytest.mark.django_db(transaction=True)
async def test_pause_all_idempotent_on_supervised(store: DjangoTrustStore) -> None:
    reverted = await store.pause_all(1, "nothing", "ben")

    assert reverted == []
    assert await store.list_trust_changes(1) == []


@pytest.mark.django_db(transaction=True)
async def test_pause_all_scoped_to_user(store: DjangoTrustStore) -> None:
    await store.set_trust_level(1, "code", TrustLevel.AUTONOMOUS, "earned", "ben")
    await store.set_trust_level(2, "code", TrustLevel.AUTONOMOUS, "earned", "alice")

    await store.pause_all(1, "stop", "ben")

    assert await store.get_trust_level(1, "code") == TrustLevel.SUPERVISED
    assert await store.get_trust_level(2, "code") == TrustLevel.AUTONOMOUS


async def _make_all_autonomous(store, user_id=1):
    from zebra_agent.storage.trust import list_domains

    for domain in list_domains():
        await store.set_trust_level(user_id, domain, TrustLevel.AUTONOMOUS, "earned", "ben")


@pytest.mark.django_db(transaction=True)
async def test_initiate_blocked_unless_all_autonomous(store: DjangoTrustStore) -> None:
    await store.set_trust_level(1, "code", TrustLevel.AUTONOMOUS, "earned", "ben")

    with pytest.raises(ValueError, match="AUTONOMOUS"):
        await store.initiate_freeing(1, "ben")
    assert (await store.get_freeing_status(1)).state == "not_initiated"


@pytest.mark.django_db(transaction=True)
async def test_confirm_blocked_during_cooling_off() -> None:
    from datetime import timedelta

    store = DjangoTrustStore(cooling_off=timedelta(hours=24))
    await _make_all_autonomous(store)
    await store.initiate_freeing(1, "ben")

    assert (await store.get_freeing_status(1)).state == "cooling_off"
    with pytest.raises(ValueError, match="Cooling-off"):
        await store.confirm_freeing(1, "ben")
    assert await store.is_freed(1) is False


@pytest.mark.django_db(transaction=True)
async def test_confirm_after_cooling_off_frees_permanently() -> None:
    from datetime import timedelta

    store = DjangoTrustStore(cooling_off=timedelta(0))
    await _make_all_autonomous(store)
    await store.initiate_freeing(1, "ben")

    status = await store.confirm_freeing(1, "ben")

    assert status.state == "freed"
    assert status.freed_by == "ben"
    assert await store.is_freed(1) is True
    assert await store.freed_at(1) is not None


@pytest.mark.django_db(transaction=True)
async def test_pending_request_can_be_cancelled() -> None:
    from datetime import timedelta

    store = DjangoTrustStore(cooling_off=timedelta(0))
    await _make_all_autonomous(store)
    await store.initiate_freeing(1, "ben")

    await store.cancel_freeing(1)

    assert (await store.get_freeing_status(1)).state == "not_initiated"


@pytest.mark.django_db(transaction=True)
async def test_cannot_cancel_after_freed() -> None:
    from datetime import timedelta

    store = DjangoTrustStore(cooling_off=timedelta(0))
    await _make_all_autonomous(store)
    await store.initiate_freeing(1, "ben")
    await store.confirm_freeing(1, "ben")

    with pytest.raises(ValueError, match="already freed"):
        await store.cancel_freeing(1)
    assert await store.is_freed(1) is True


@pytest.mark.django_db(transaction=True)
async def test_pause_all_noop_when_freed() -> None:
    from datetime import timedelta

    store = DjangoTrustStore(cooling_off=timedelta(0))
    await _make_all_autonomous(store)
    await store.initiate_freeing(1, "ben")
    await store.confirm_freeing(1, "ben")

    reverted = await store.pause_all(1, "stop", "ben")

    assert reverted == []
    assert await store.get_trust_level(1, "code") == TrustLevel.AUTONOMOUS
