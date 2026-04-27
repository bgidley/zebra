"""Values-profile dataclasses.

A user's values profile is a versioned record of four free-form text fields
(core values, ethical positions, priorities, deal-breakers) plus structured
tags extracted from those texts. Each save creates an immutable
``ValuesProfileVersion``; the store tracks the latest version per user.

For storage backends, implement the ``ProfileStore`` interface from
``zebra_agent.storage.interfaces``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ValuesProfileVersion:
    """An immutable snapshot of a user's values profile at a point in time.

    Each save through ``ProfileStore.save_version`` creates a new instance
    with monotonically increasing ``version_number``. The ``id`` is assigned
    by the store and ``version_number`` is auto-incremented per user.
    """

    core_values_text: str = ""
    core_values_tags: list[str] = field(default_factory=list)
    ethical_positions_text: str = ""
    ethical_positions_tags: list[str] = field(default_factory=list)
    priorities_text: str = ""
    priorities_tags: list[str] = field(default_factory=list)
    deal_breakers_text: str = ""
    deal_breakers_tags: list[str] = field(default_factory=list)
    tags_extracted_at: datetime | None = None
    tags_extraction_model: str | None = None
    created_via: str = "wizard"

    # Store-assigned fields. Drafts may leave these blank; the store fills
    # them in on save_version() and returns the populated instance.
    id: str = ""
    version_number: int = 0
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (for serialisation into process properties)."""
        return {
            "id": self.id,
            "version_number": self.version_number,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_via": self.created_via,
            "core_values_text": self.core_values_text,
            "core_values_tags": list(self.core_values_tags),
            "ethical_positions_text": self.ethical_positions_text,
            "ethical_positions_tags": list(self.ethical_positions_tags),
            "priorities_text": self.priorities_text,
            "priorities_tags": list(self.priorities_tags),
            "deal_breakers_text": self.deal_breakers_text,
            "deal_breakers_tags": list(self.deal_breakers_tags),
            "tags_extracted_at": (
                self.tags_extracted_at.isoformat() if self.tags_extracted_at else None
            ),
            "tags_extraction_model": self.tags_extraction_model,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValuesProfileVersion:
        """Inverse of ``to_dict``."""

        def _maybe_dt(value: str | None) -> datetime | None:
            return datetime.fromisoformat(value) if value else None

        return cls(
            id=data.get("id", ""),
            version_number=data.get("version_number", 0),
            created_at=_maybe_dt(data.get("created_at")),
            created_via=data.get("created_via", "wizard"),
            core_values_text=data.get("core_values_text", ""),
            core_values_tags=list(data.get("core_values_tags", [])),
            ethical_positions_text=data.get("ethical_positions_text", ""),
            ethical_positions_tags=list(data.get("ethical_positions_tags", [])),
            priorities_text=data.get("priorities_text", ""),
            priorities_tags=list(data.get("priorities_tags", [])),
            deal_breakers_text=data.get("deal_breakers_text", ""),
            deal_breakers_tags=list(data.get("deal_breakers_tags", [])),
            tags_extracted_at=_maybe_dt(data.get("tags_extracted_at")),
            tags_extraction_model=data.get("tags_extraction_model"),
        )


def _utc_now() -> datetime:
    """Return the current UTC timestamp (extracted for test patching)."""
    return datetime.now(UTC)


__all__ = ["ValuesProfileVersion", "_utc_now"]
