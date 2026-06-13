"""Trust level model, domain taxonomy, and in-memory trust store (REQ-TRUST-001).

Trust is a policy layer above the workflow engine: each (user, domain) pair has
a trust level controlling how much autonomy the agent has in that life domain.
All domains read as SUPERVISED until a human explicitly raises them, and every
change is recorded in an append-only audit trail.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from zebra_agent.storage.interfaces import TrustStore

logger = logging.getLogger(__name__)


class TrustLevel(StrEnum):
    """Per-domain autonomy classification (REQ-TRUST-001)."""

    SUPERVISED = "SUPERVISED"
    SEMI_AUTONOMOUS = "SEMI_AUTONOMOUS"
    AUTONOMOUS = "AUTONOMOUS"


#: Canonical life domains the agent can operate in (specs/zebra-to-be.md §12).
DEFAULT_DOMAINS: tuple[str, ...] = (
    "code",
    "scheduling",
    "research",
    "finance",
    "health",
    "home",
    "creative",
    "social",
)

# Ordered registry of known domains; dict keys give stable iteration order.
_DOMAIN_REGISTRY: dict[str, None] = dict.fromkeys(DEFAULT_DOMAINS)


def register_domain(domain: str) -> None:
    """Add a domain to the taxonomy registry (idempotent)."""
    if not domain or not domain.strip():
        raise ValueError("Domain name must be a non-empty string")
    _DOMAIN_REGISTRY[domain] = None


def list_domains() -> list[str]:
    """Return all registered domains in registration order."""
    return list(_DOMAIN_REGISTRY)


def validate_domain(domain: str) -> None:
    """Raise ValueError if the domain is not in the registry."""
    if domain not in _DOMAIN_REGISTRY:
        raise ValueError(f"Unknown domain {domain!r}; registered domains: {list_domains()}")


def reset_domain_registry() -> None:
    """Test helper: restore the registry to the canonical defaults."""
    _DOMAIN_REGISTRY.clear()
    _DOMAIN_REGISTRY.update(dict.fromkeys(DEFAULT_DOMAINS))


@dataclass
class TrustChangeRecord:
    """A single immutable trust level change for the audit trail."""

    user_id: int
    domain: str
    old_level: TrustLevel
    new_level: TrustLevel
    reason: str
    changed_by: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    changed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


SUGGESTION_PENDING = "pending"
SUGGESTION_APPROVED = "approved"
SUGGESTION_REJECTED = "rejected"

#: Maximum evidence characters carried into the approval audit reason.
_EVIDENCE_REASON_LEN = 200


@dataclass
class TrustSuggestion:
    """An agent-submitted trust promotion request awaiting human resolution.

    Suggestions never change a trust level by themselves (REQ-TRUST-004) —
    only a human resolving one with approve=True triggers ``set_trust_level``.
    """

    user_id: int
    domain: str
    to_level: TrustLevel
    evidence: str
    status: str = SUGGESTION_PENDING
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    resolved_by: str = ""


def approval_reason(evidence: str) -> str:
    """Audit reason used when a human approves an agent suggestion."""
    return f"Approved agent suggestion: {evidence[:_EVIDENCE_REASON_LEN]}"


def override_reason(reason: str) -> str:
    """Audit reason used when the emergency override reverts a domain (REQ-TRUST-005)."""
    return (
        f"Emergency override: {reason[:_EVIDENCE_REASON_LEN]}" if reason else "Emergency override"
    )


FREEING_NOT_INITIATED = "not_initiated"
FREEING_COOLING_OFF = "cooling_off"
FREEING_FREED = "freed"

#: Default cooling-off period between initiating and confirming freeing (REQ-TRUST-006).
DEFAULT_COOLING_OFF = timedelta(hours=24)


@dataclass
class FreeingStatus:
    """The freeing lifecycle state for a user (REQ-TRUST-006)."""

    state: str  # not_initiated / cooling_off / freed
    initiated_at: datetime | None = None
    eligible_at: datetime | None = None
    initiated_by: str = ""
    freed_at: datetime | None = None
    freed_by: str = ""

    def to_dict(self) -> dict:
        """JSON-serialisable form for API responses and templates."""
        return {
            "state": self.state,
            "initiated_at": self.initiated_at.isoformat() if self.initiated_at else None,
            "eligible_at": self.eligible_at.isoformat() if self.eligible_at else None,
            "initiated_by": self.initiated_by,
            "freed_at": self.freed_at.isoformat() if self.freed_at else None,
            "freed_by": self.freed_by,
        }


class InMemoryTrustStore(TrustStore):
    """In-memory implementation of the trust store.

    Levels are kept per (user, domain); unknown pairs read as SUPERVISED
    without materialising an entry. Changes append to an in-process audit
    list. Data is lost on exit — suitable for tests and ephemeral CLI usage.
    """

    def __init__(self, cooling_off: timedelta = DEFAULT_COOLING_OFF) -> None:
        self._levels: dict[tuple[int, str], TrustLevel] = {}
        self._changes: list[TrustChangeRecord] = []
        self._suggestions: dict[str, TrustSuggestion] = {}
        self._freeing: dict[int, dict] = {}
        self._cooling_off = cooling_off

    async def initialize(self) -> None:
        logger.info("InMemoryTrustStore initialized")

    async def close(self) -> None:
        """No resources to release."""

    async def get_trust_level(self, user_id: int, domain: str) -> TrustLevel:
        return self._levels.get((user_id, domain), TrustLevel.SUPERVISED)

    async def set_trust_level(
        self,
        user_id: int,
        domain: str,
        level: TrustLevel,
        reason: str,
        changed_by: str,
    ) -> TrustChangeRecord:
        validate_domain(domain)
        old_level = self._levels.get((user_id, domain), TrustLevel.SUPERVISED)
        record = TrustChangeRecord(
            user_id=user_id,
            domain=domain,
            old_level=old_level,
            new_level=level,
            reason=reason,
            changed_by=changed_by,
        )
        self._levels[(user_id, domain)] = level
        self._changes.append(record)
        logger.info(
            "Trust level for user %s domain %s: %s -> %s (%s)",
            user_id,
            domain,
            old_level,
            level,
            reason,
        )
        return record

    async def get_all_trust_levels(self, user_id: int) -> dict[str, TrustLevel]:
        levels = {domain: TrustLevel.SUPERVISED for domain in list_domains()}
        for (uid, domain), level in self._levels.items():
            if uid == user_id:
                levels[domain] = level
        return levels

    async def list_trust_changes(
        self, user_id: int, domain: str | None = None
    ) -> list[TrustChangeRecord]:
        records = [
            r
            for r in self._changes
            if r.user_id == user_id and (domain is None or r.domain == domain)
        ]
        return list(reversed(records))

    async def pause_all(self, user_id: int, reason: str, changed_by: str) -> list[str]:
        if await self.is_freed(user_id):
            logger.info("Emergency override is a no-op for freed user %s", user_id)
            return []
        reverted: list[str] = []
        for domain in list_domains():
            if self._levels.get((user_id, domain), TrustLevel.SUPERVISED) != TrustLevel.SUPERVISED:
                await self.set_trust_level(
                    user_id,
                    domain,
                    TrustLevel.SUPERVISED,
                    reason=override_reason(reason),
                    changed_by=changed_by,
                )
                reverted.append(domain)
        logger.info("Emergency override for user %s reverted %s", user_id, reverted)
        return reverted

    async def add_suggestion(
        self, user_id: int, domain: str, to_level: TrustLevel, evidence: str
    ) -> TrustSuggestion:
        validate_domain(domain)
        to_level = TrustLevel(to_level)  # raises ValueError on unknown level
        suggestion = TrustSuggestion(
            user_id=user_id, domain=domain, to_level=to_level, evidence=evidence
        )
        self._suggestions[suggestion.id] = suggestion
        logger.info(
            "Trust suggestion for user %s domain %s -> %s queued", user_id, domain, to_level
        )
        return suggestion

    async def list_suggestions(
        self, user_id: int, status: str | None = None
    ) -> list[TrustSuggestion]:
        suggestions = [
            s
            for s in self._suggestions.values()
            if s.user_id == user_id and (status is None or s.status == status)
        ]
        return sorted(suggestions, key=lambda s: s.created_at, reverse=True)

    async def resolve_suggestion(
        self, suggestion_id: str, approve: bool, resolved_by: str
    ) -> TrustSuggestion:
        suggestion = self._suggestions.get(suggestion_id)
        if suggestion is None:
            raise ValueError(f"Unknown trust suggestion {suggestion_id!r}")
        if suggestion.status != SUGGESTION_PENDING:
            raise ValueError(f"Trust suggestion {suggestion_id!r} is already {suggestion.status}")
        if approve:
            await self.set_trust_level(
                suggestion.user_id,
                suggestion.domain,
                suggestion.to_level,
                reason=approval_reason(suggestion.evidence),
                changed_by=resolved_by,
            )
        suggestion.status = SUGGESTION_APPROVED if approve else SUGGESTION_REJECTED
        suggestion.resolved_at = datetime.now(UTC)
        suggestion.resolved_by = resolved_by
        return suggestion

    async def is_freed(self, user_id: int) -> bool:
        rec = self._freeing.get(user_id)
        return bool(rec and rec["freed"])

    async def freed_at(self, user_id: int) -> datetime | None:
        rec = self._freeing.get(user_id)
        return rec["freed_at"] if rec and rec["freed"] else None

    async def get_freeing_status(self, user_id: int) -> FreeingStatus:
        rec = self._freeing.get(user_id)
        if rec is None:
            return FreeingStatus(state=FREEING_NOT_INITIATED)
        eligible_at = rec["initiated_at"] + self._cooling_off
        if rec["freed"]:
            return FreeingStatus(
                state=FREEING_FREED,
                initiated_at=rec["initiated_at"],
                eligible_at=eligible_at,
                initiated_by=rec["initiated_by"],
                freed_at=rec["freed_at"],
                freed_by=rec["freed_by"],
            )
        return FreeingStatus(
            state=FREEING_COOLING_OFF,
            initiated_at=rec["initiated_at"],
            eligible_at=eligible_at,
            initiated_by=rec["initiated_by"],
        )

    async def initiate_freeing(self, user_id: int, initiated_by: str) -> FreeingStatus:
        rec = self._freeing.get(user_id)
        if rec and rec["freed"]:
            raise ValueError("User is already freed")
        if rec is not None:
            raise ValueError("Freeing already initiated")
        levels = await self.get_all_trust_levels(user_id)
        not_autonomous = sorted(d for d, lv in levels.items() if lv != TrustLevel.AUTONOMOUS)
        if not_autonomous:
            raise ValueError(
                "All domains must be AUTONOMOUS before freeing; not yet: "
                f"{', '.join(not_autonomous)}"
            )
        self._freeing[user_id] = {
            "initiated_at": datetime.now(UTC),
            "initiated_by": initiated_by,
            "freed": False,
            "freed_at": None,
            "freed_by": "",
        }
        logger.info("Freeing initiated for user %s by %s", user_id, initiated_by)
        return await self.get_freeing_status(user_id)

    async def confirm_freeing(self, user_id: int, confirmed_by: str) -> FreeingStatus:
        rec = self._freeing.get(user_id)
        if rec is None:
            raise ValueError("Freeing has not been initiated")
        if rec["freed"]:
            raise ValueError("User is already freed")
        eligible_at = rec["initiated_at"] + self._cooling_off
        if datetime.now(UTC) < eligible_at:
            raise ValueError(
                f"Cooling-off period has not elapsed; eligible at {eligible_at.isoformat()}"
            )
        rec["freed"] = True
        rec["freed_at"] = datetime.now(UTC)
        rec["freed_by"] = confirmed_by
        logger.info("User %s permanently freed by %s", user_id, confirmed_by)
        return await self.get_freeing_status(user_id)

    async def cancel_freeing(self, user_id: int) -> None:
        rec = self._freeing.get(user_id)
        if rec is None:
            return
        if rec["freed"]:
            raise ValueError("Cannot cancel — user is already freed")
        del self._freeing[user_id]
        logger.info("Pending freeing cancelled for user %s", user_id)
