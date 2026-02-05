"""Memory dataclasses and in-memory storage for agent conversations.

This module provides:
- Data classes for memory entries, summaries, and themes
- In-memory storage implementation (via re-export)
- Token estimation utility

For custom storage backends, implement the MemoryStore interface from
zebra_agent.storage.interfaces.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zebra_agent.storage.memory import InMemoryMemoryStore


@dataclass
class MemoryEntry:
    """A single memory entry representing an agent interaction."""

    id: str
    timestamp: datetime
    goal: str
    workflow_used: str
    result_summary: str
    tokens: int

    @classmethod
    def create(
        cls,
        goal: str,
        workflow_used: str,
        result_summary: str,
        tokens: int | None = None,
    ) -> "MemoryEntry":
        """Create a new memory entry with auto-generated ID and timestamp.

        Args:
            goal: The user's goal or request
            workflow_used: Name of the workflow that was used
            result_summary: Summary of the result
            tokens: Token count (if None, will be estimated from result_summary)

        Returns:
            A new MemoryEntry instance
        """
        if tokens is None:
            tokens = estimate_tokens(result_summary)

        return cls(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            goal=goal,
            workflow_used=workflow_used,
            result_summary=result_summary,
            tokens=tokens,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert entry to dictionary for serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "goal": self.goal,
            "workflow_used": self.workflow_used,
            "result_summary": self.result_summary,
            "tokens": self.tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEntry":
        """Create entry from dictionary."""
        return cls(
            id=data["id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            goal=data["goal"],
            workflow_used=data["workflow_used"],
            result_summary=data["result_summary"],
            tokens=data["tokens"],
        )


@dataclass
class ShortTermSummary:
    """A compacted short-term memory summary."""

    id: str
    created_at: datetime
    summary: str
    tokens: int
    entry_count: int  # How many entries were summarized

    @classmethod
    def create(
        cls,
        summary: str,
        entry_count: int,
        tokens: int | None = None,
    ) -> "ShortTermSummary":
        """Create a new short-term summary with auto-generated ID and timestamp.

        Args:
            summary: The compacted summary text
            entry_count: Number of entries that were summarized
            tokens: Token count (if None, will be estimated from summary)

        Returns:
            A new ShortTermSummary instance
        """
        if tokens is None:
            tokens = estimate_tokens(summary)

        return cls(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            summary=summary,
            tokens=tokens,
            entry_count=entry_count,
        )


@dataclass
class LongTermTheme:
    """A long-term memory theme extracted from short-term summaries."""

    id: str
    created_at: datetime
    theme: str
    tokens: int
    short_term_refs: list[str]  # IDs of short-term summaries this references

    @classmethod
    def create(
        cls,
        theme: str,
        short_term_refs: list[str] | None = None,
        tokens: int | None = None,
    ) -> "LongTermTheme":
        """Create a new long-term theme with auto-generated ID and timestamp.

        Args:
            theme: The theme text
            short_term_refs: List of short-term summary IDs this theme references
            tokens: Token count (if None, will be estimated from theme)

        Returns:
            A new LongTermTheme instance
        """
        if tokens is None:
            tokens = estimate_tokens(theme)

        return cls(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            theme=theme,
            tokens=tokens,
            short_term_refs=short_term_refs or [],
        )


def estimate_tokens(text: str) -> int:
    """Rough estimate of tokens in text (chars / 4).

    This is a simple heuristic that works reasonably well for English text.
    For more accurate token counting, use a proper tokenizer.

    Args:
        text: The text to estimate tokens for

    Returns:
        Estimated number of tokens
    """
    return len(text) // 4


def __getattr__(name: str):
    """Lazy import for AgentMemory to avoid circular import."""
    if name == "AgentMemory":
        from zebra_agent.storage.memory import InMemoryMemoryStore

        return InMemoryMemoryStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "MemoryEntry",
    "ShortTermSummary",
    "LongTermTheme",
    "AgentMemory",
    "estimate_tokens",
]
