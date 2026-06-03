"""Personal knowledge store dataclasses and constants.

Defines the KnowledgeEntry dataclass and category constants for the
personal knowledge tier — typed, user-scoped facts, preferences, and
structured knowledge that the agent reads during planning.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

KNOWLEDGE_CATEGORIES: tuple[str, ...] = (
    "preferences",
    "facts",
    "relationships",
    "routines",
    "skills",
    "history",
)

# Exponential decay half-life in days per category.
# None means the category is never decayed (audit/historical data).
# Only entries with time_sensitive=True are subject to decay.
CATEGORY_DECAY_HALF_LIFE_DAYS: dict[str, int | None] = {
    "preferences": 180,
    "facts": 365,
    "relationships": 90,
    "routines": 60,
    "skills": 730,
    "history": None,
}

# Minimum confidence floor — decay never reduces below this value.
CONFIDENCE_DECAY_FLOOR = 0.1


@dataclass
class KnowledgeEntry:
    """A single personal knowledge entry scoped to a user."""

    id: str
    user_id: int
    category: str
    key: str
    value: str
    source: str  # "human" or "agent"
    confidence: float
    last_verified: datetime
    created_at: datetime
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    time_sensitive: bool = False
    deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.category not in KNOWLEDGE_CATEGORIES:
            raise ValueError(
                f"Invalid category {self.category!r}. "
                f"Must be one of: {', '.join(KNOWLEDGE_CATEGORIES)}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {self.confidence}")

    @property
    def is_deleted(self) -> bool:
        """Return True if this entry has been soft-deleted."""
        return self.deleted_at is not None

    @classmethod
    def create(
        cls,
        user_id: int,
        category: str,
        key: str,
        value: str,
        source: str = "human",
        confidence: float = 1.0,
        time_sensitive: bool = False,
    ) -> KnowledgeEntry:
        """Create a new entry with auto-generated ID and timestamps."""
        now = datetime.now(UTC)
        return cls(
            id=str(uuid.uuid4()),
            user_id=user_id,
            category=category,
            key=key,
            value=value,
            source=source,
            confidence=confidence,
            last_verified=now,
            created_at=now,
            updated_at=now,
            time_sensitive=time_sensitive,
            deleted_at=None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "category": self.category,
            "key": self.key,
            "value": self.value,
            "source": self.source,
            "confidence": self.confidence,
            "last_verified": self.last_verified.isoformat(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "time_sensitive": self.time_sensitive,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KnowledgeEntry:
        """Create from dictionary."""
        deleted_at_raw = data.get("deleted_at")
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            category=data["category"],
            key=data["key"],
            value=data["value"],
            source=data.get("source", "human"),
            confidence=data.get("confidence", 1.0),
            last_verified=datetime.fromisoformat(data["last_verified"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data.get("updated_at", data["created_at"])),
            time_sensitive=data.get("time_sensitive", False),
            deleted_at=datetime.fromisoformat(deleted_at_raw) if deleted_at_raw else None,
        )


__all__ = [
    "KnowledgeEntry",
    "KNOWLEDGE_CATEGORIES",
    "CATEGORY_DECAY_HALF_LIFE_DAYS",
    "CONFIDENCE_DECAY_FLOOR",
]
