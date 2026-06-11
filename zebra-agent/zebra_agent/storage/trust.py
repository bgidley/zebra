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
from datetime import UTC, datetime
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


class InMemoryTrustStore(TrustStore):
    """In-memory implementation of the trust store.

    Levels are kept per (user, domain); unknown pairs read as SUPERVISED
    without materialising an entry. Changes append to an in-process audit
    list. Data is lost on exit — suitable for tests and ephemeral CLI usage.
    """

    def __init__(self) -> None:
        self._levels: dict[tuple[int, str], TrustLevel] = {}
        self._changes: list[TrustChangeRecord] = []

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
