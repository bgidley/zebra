"""Memory dataclasses for workflow-focused agent memory.

Two-tier memory system:
- WorkflowMemoryEntry: Detailed per-run record of workflow behaviour, I/O, effectiveness
- ConceptualMemoryEntry: Compact index mapping goal patterns to recommended workflows

For custom storage backends, implement the MemoryStore interface from
zebra_agent.storage.interfaces.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


@dataclass
class WorkflowMemoryEntry:
    """A detailed record of a single workflow run's behaviour and effectiveness."""

    id: str
    timestamp: datetime
    workflow_name: str
    goal: str
    success: bool
    input_summary: str  # What went into the workflow
    output_summary: str  # What came out
    effectiveness_notes: str  # LLM assessment of what worked / didn't
    tokens_used: int
    rating: int | None = None  # User rating 1-5 if provided

    @classmethod
    def create(
        cls,
        workflow_name: str,
        goal: str,
        success: bool,
        input_summary: str,
        output_summary: str,
        effectiveness_notes: str,
        tokens_used: int = 0,
        rating: int | None = None,
    ) -> WorkflowMemoryEntry:
        """Create a new entry with auto-generated ID and timestamp."""
        return cls(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC),
            workflow_name=workflow_name,
            goal=goal,
            success=success,
            input_summary=input_summary,
            output_summary=output_summary,
            effectiveness_notes=effectiveness_notes,
            tokens_used=tokens_used,
            rating=rating,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "workflow_name": self.workflow_name,
            "goal": self.goal,
            "success": self.success,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "effectiveness_notes": self.effectiveness_notes,
            "tokens_used": self.tokens_used,
            "rating": self.rating,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowMemoryEntry:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            workflow_name=data["workflow_name"],
            goal=data["goal"],
            success=data["success"],
            input_summary=data["input_summary"],
            output_summary=data["output_summary"],
            effectiveness_notes=data["effectiveness_notes"],
            tokens_used=data.get("tokens_used", 0),
            rating=data.get("rating"),
        )


@dataclass
class ConceptualMemoryEntry:
    """A compact index entry mapping a goal pattern to recommended workflows.

    Built by compacting WorkflowMemoryEntry records. The conceptual memory
    is what the agent consults first to produce a shortlist of candidates.
    """

    id: str
    concept: str  # Goal pattern / category description
    recommended_workflows: list[dict]  # [{name, fit_notes, avg_rating, use_count}]
    anti_patterns: str  # What doesn't work for this concept
    last_updated: datetime
    tokens: int = 0

    @classmethod
    def create(
        cls,
        concept: str,
        recommended_workflows: list[dict] | None = None,
        anti_patterns: str = "",
        tokens: int | None = None,
    ) -> ConceptualMemoryEntry:
        """Create a new entry with auto-generated ID and timestamp."""
        text = concept + anti_patterns
        if recommended_workflows:
            text += str(recommended_workflows)
        return cls(
            id=str(uuid.uuid4()),
            concept=concept,
            recommended_workflows=recommended_workflows or [],
            anti_patterns=anti_patterns,
            last_updated=datetime.now(UTC),
            tokens=tokens if tokens is not None else estimate_tokens(text),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "concept": self.concept,
            "recommended_workflows": self.recommended_workflows,
            "anti_patterns": self.anti_patterns,
            "last_updated": self.last_updated.isoformat(),
            "tokens": self.tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConceptualMemoryEntry:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            concept=data["concept"],
            recommended_workflows=data.get("recommended_workflows", []),
            anti_patterns=data.get("anti_patterns", ""),
            last_updated=datetime.fromisoformat(data["last_updated"]),
            tokens=data.get("tokens", 0),
        )


def estimate_tokens(text: str) -> int:
    """Rough estimate of tokens in text (chars / 4).

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
    "WorkflowMemoryEntry",
    "ConceptualMemoryEntry",
    "AgentMemory",  # noqa: F822 - resolved via __getattr__ (backward-compat alias for InMemoryMemoryStore)
    "estimate_tokens",
]
