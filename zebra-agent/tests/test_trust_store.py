"""Tests for the trust level data model and InMemoryTrustStore (F12 / REQ-TRUST-001)."""

import pytest

from zebra_agent.storage.trust import (
    DEFAULT_DOMAINS,
    InMemoryTrustStore,
    TrustLevel,
    list_domains,
    register_domain,
    reset_domain_registry,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_domain_registry()
    yield
    reset_domain_registry()


@pytest.fixture
async def store():
    s = InMemoryTrustStore()
    await s.initialize()
    return s


async def test_unset_domain_reads_as_supervised(store):
    assert await store.get_trust_level(1, "finance") == TrustLevel.SUPERVISED
    # Reading must not materialise a stored level
    assert store._levels == {}


async def test_set_then_read_back(store):
    await store.set_trust_level(1, "code", TrustLevel.SEMI_AUTONOMOUS, "20 clean runs", "ben")
    assert await store.get_trust_level(1, "code") == TrustLevel.SEMI_AUTONOMOUS


async def test_trust_levels_are_user_scoped(store):
    await store.set_trust_level(1, "code", TrustLevel.AUTONOMOUS, "earned", "ben")
    assert await store.get_trust_level(2, "code") == TrustLevel.SUPERVISED


async def test_unknown_domain_rejected_on_write(store):
    with pytest.raises(ValueError, match="time-travel"):
        await store.set_trust_level(1, "time-travel", TrustLevel.AUTONOMOUS, "nope", "ben")
    assert store._levels == {}
    assert await store.list_trust_changes(1) == []


async def test_get_all_trust_levels_merges_defaults(store):
    await store.set_trust_level(1, "code", TrustLevel.SEMI_AUTONOMOUS, "earned", "ben")
    levels = await store.get_all_trust_levels(1)
    assert set(levels) == set(DEFAULT_DOMAINS)
    assert levels["code"] == TrustLevel.SEMI_AUTONOMOUS
    others = {d: lv for d, lv in levels.items() if d != "code"}
    assert all(lv == TrustLevel.SUPERVISED for lv in others.values())
    assert len(others) == len(DEFAULT_DOMAINS) - 1


async def test_registered_custom_domain_accepted(store):
    register_domain("gardening")
    await store.set_trust_level(1, "gardening", TrustLevel.SEMI_AUTONOMOUS, "trial", "ben")
    levels = await store.get_all_trust_levels(1)
    assert levels["gardening"] == TrustLevel.SEMI_AUTONOMOUS
    assert "gardening" in list_domains()


async def test_register_domain_rejects_blank():
    with pytest.raises(ValueError):
        register_domain("  ")


async def test_change_writes_audit_record(store):
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


async def test_history_accumulates_newest_first(store):
    await store.set_trust_level(1, "code", TrustLevel.SEMI_AUTONOMOUS, "step 1", "ben")
    await store.set_trust_level(1, "code", TrustLevel.AUTONOMOUS, "step 2", "ben")
    await store.set_trust_level(1, "code", TrustLevel.SUPERVISED, "step 3", "ben")

    changes = await store.list_trust_changes(1, "code")
    assert [c.reason for c in changes] == ["step 3", "step 2", "step 1"]
    # old/new levels chain consistently (newest first)
    assert changes[0].old_level == changes[1].new_level
    assert changes[1].old_level == changes[2].new_level
    assert changes[2].old_level == TrustLevel.SUPERVISED


async def test_list_trust_changes_filters_by_domain_and_user(store):
    await store.set_trust_level(1, "code", TrustLevel.SEMI_AUTONOMOUS, "a", "ben")
    await store.set_trust_level(1, "home", TrustLevel.AUTONOMOUS, "b", "ben")
    await store.set_trust_level(2, "code", TrustLevel.AUTONOMOUS, "c", "alice")

    assert [c.reason for c in await store.list_trust_changes(1)] == ["b", "a"]
    assert [c.reason for c in await store.list_trust_changes(1, "code")] == ["a"]
    assert [c.reason for c in await store.list_trust_changes(2)] == ["c"]


class TestSuggestions:
    """Agent promotion suggestions (F15 / REQ-TRUST-004)."""

    async def test_add_suggestion_is_pending_and_changes_nothing(self, store):
        suggestion = await store.add_suggestion(
            1, "code", TrustLevel.SEMI_AUTONOMOUS, "20 clean runs"
        )

        assert suggestion.status == "pending"
        assert suggestion.evidence == "20 clean runs"
        assert await store.get_trust_level(1, "code") == TrustLevel.SUPERVISED
        assert await store.list_trust_changes(1) == []

    async def test_add_suggestion_validates_domain_and_level(self, store):
        with pytest.raises(ValueError, match="time-travel"):
            await store.add_suggestion(1, "time-travel", TrustLevel.AUTONOMOUS, "x")
        with pytest.raises(ValueError):
            await store.add_suggestion(1, "code", "OMNIPOTENT", "x")
        assert await store.list_suggestions(1) == []

    async def test_list_suggestions_filters_by_user_and_status(self, store):
        s1 = await store.add_suggestion(1, "code", TrustLevel.SEMI_AUTONOMOUS, "a")
        await store.add_suggestion(1, "home", TrustLevel.AUTONOMOUS, "b")
        await store.add_suggestion(2, "code", TrustLevel.AUTONOMOUS, "c")
        await store.resolve_suggestion(s1.id, approve=False, resolved_by="ben")

        assert len(await store.list_suggestions(1)) == 2
        pending = await store.list_suggestions(1, status="pending")
        assert [s.evidence for s in pending] == ["b"]
        assert [s.evidence for s in await store.list_suggestions(2)] == ["c"]

    async def test_approve_changes_level_and_audits_resolver(self, store):
        suggestion = await store.add_suggestion(
            1, "code", TrustLevel.SEMI_AUTONOMOUS, "20 clean runs"
        )

        resolved = await store.resolve_suggestion(suggestion.id, approve=True, resolved_by="ben")

        assert resolved.status == "approved"
        assert resolved.resolved_by == "ben"
        assert resolved.resolved_at is not None
        assert await store.get_trust_level(1, "code") == TrustLevel.SEMI_AUTONOMOUS
        changes = await store.list_trust_changes(1, "code")
        assert len(changes) == 1
        assert changes[0].changed_by == "ben"
        assert "20 clean runs" in changes[0].reason

    async def test_reject_leaves_level_untouched(self, store):
        suggestion = await store.add_suggestion(1, "code", TrustLevel.AUTONOMOUS, "trust me")

        resolved = await store.resolve_suggestion(suggestion.id, approve=False, resolved_by="ben")

        assert resolved.status == "rejected"
        assert await store.get_trust_level(1, "code") == TrustLevel.SUPERVISED
        assert await store.list_trust_changes(1) == []

    async def test_double_resolution_rejected(self, store):
        suggestion = await store.add_suggestion(1, "code", TrustLevel.AUTONOMOUS, "x")
        await store.resolve_suggestion(suggestion.id, approve=False, resolved_by="ben")

        with pytest.raises(ValueError, match="already"):
            await store.resolve_suggestion(suggestion.id, approve=True, resolved_by="ben")
        assert await store.get_trust_level(1, "code") == TrustLevel.SUPERVISED

    async def test_unknown_suggestion_rejected(self, store):
        with pytest.raises(ValueError, match="Unknown"):
            await store.resolve_suggestion("nope", approve=True, resolved_by="ben")
