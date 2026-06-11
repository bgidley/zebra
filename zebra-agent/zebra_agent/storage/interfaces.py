"""Abstract base classes for agent storage backends.

This module defines the interfaces for memory and metrics storage that can be
implemented by different backends (in-memory, Django ORM, PostgreSQL, etc.).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from zebra_agent.memory import ConceptualMemoryEntry, WorkflowMemoryEntry

if TYPE_CHECKING:
    from zebra_agent.knowledge import KnowledgeEntry
    from zebra_agent.metrics import TaskExecution, WorkflowRun, WorkflowStats
    from zebra_agent.profile import ValuesProfileVersion
    from zebra_agent.storage.trust import TrustChangeRecord, TrustLevel


@dataclass
class CompactionBatch:
    """Entries that need tier transitions, grouped by direction and type."""

    warm_workflow: list[WorkflowMemoryEntry] = field(default_factory=list)
    cold_workflow: list[WorkflowMemoryEntry] = field(default_factory=list)
    warm_conceptual: list[ConceptualMemoryEntry] = field(default_factory=list)
    cold_conceptual: list[ConceptualMemoryEntry] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.warm_workflow or self.cold_workflow or self.warm_conceptual or self.cold_conceptual
        )


@dataclass
class EthicsAuditEntry:
    """A single immutable ethics evaluation record."""

    process_id: str
    goal: str
    approved: bool
    overall_reasoning: str
    check_type: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: int | None = None
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class MemoryStore(ABC):
    """Abstract interface for workflow-focused agent memory storage.

    Two-tier memory system:
    - Workflow Memory: Detailed per-run records of behaviour, I/O, effectiveness
    - Conceptual Memory: Compact index mapping goal patterns to workflow names

    The agent consults conceptual memory first to get a shortlist of candidates,
    then loads full details for deep selection. After each run, workflow memory
    is written and conceptual memory is incrementally updated.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the memory store."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the memory store and release resources."""
        ...

    # =========================================================================
    # Workflow Memory (Detailed per-run records)
    # =========================================================================

    @abstractmethod
    async def add_workflow_memory(self, entry: WorkflowMemoryEntry) -> None:
        """Add a detailed workflow run record to memory."""
        ...

    @abstractmethod
    async def get_workflow_memories(
        self, workflow_name: str, limit: int = 10
    ) -> list[WorkflowMemoryEntry]:
        """Get recent memory entries for a specific workflow, newest first."""
        ...

    @abstractmethod
    async def get_recent_workflow_memories(self, limit: int = 20) -> list[WorkflowMemoryEntry]:
        """Get the most recent workflow memory entries across all workflows."""
        ...

    @abstractmethod
    async def update_user_feedback(self, run_id: str, feedback: str) -> bool:
        """Update user feedback on the workflow memory entry for a run.

        Args:
            run_id: The run ID whose memory entry should be updated.
            feedback: Free-text feedback from the user.

        Returns:
            True if a matching memory entry was found and updated, False otherwise.
        """
        ...

    @abstractmethod
    async def get_workflow_memory_by_run_id(self, run_id: str) -> WorkflowMemoryEntry | None:
        """Return the workflow memory entry for a specific run, or None if not found.

        Args:
            run_id: The run ID to look up.

        Returns:
            The matching WorkflowMemoryEntry, or None if not found.
        """
        ...

    # =========================================================================
    # Conceptual Memory (Compact goal-pattern index)
    # =========================================================================

    @abstractmethod
    async def get_conceptual_memories(self, limit: int = 50) -> list[ConceptualMemoryEntry]:
        """Get all conceptual memory entries, most recently updated first."""
        ...

    @abstractmethod
    async def save_conceptual_memory(self, entry: ConceptualMemoryEntry) -> None:
        """Save (insert or update) a conceptual memory entry."""
        ...

    @abstractmethod
    async def clear_conceptual_memories(self) -> None:
        """Remove all conceptual memory entries (used during full rebuild)."""
        ...

    # =========================================================================
    # Context Generation
    # =========================================================================

    @abstractmethod
    async def get_conceptual_context_for_llm(self) -> str:
        """Format conceptual memory as a context string for the LLM.

        Returns a compact summary of goal patterns and recommended workflows,
        suitable for injecting into the workflow selection prompt.
        """
        ...

    @abstractmethod
    async def get_workflow_context_for_llm(self, workflow_name: str) -> str:
        """Format recent workflow memory for a specific workflow as LLM context.

        Returns a summary of past runs: what goals were served, what worked,
        what didn't, effectiveness notes.
        """
        ...

    @abstractmethod
    async def get_stats(self) -> dict:
        """Return memory statistics."""
        ...

    # =========================================================================
    # Compaction (Tiered retention)
    # =========================================================================

    @abstractmethod
    async def get_entries_for_compaction(self, now: datetime) -> CompactionBatch:
        """Return entries whose current tier is staler than their age warrants.

        Only returns entries that have crossed a tier boundary:
        - warm_workflow / warm_conceptual: age > 2 weeks AND current tier == "hot"
        - cold_workflow / cold_conceptual: age > 2 months AND current tier != "cold"

        Args:
            now: Reference datetime for age calculation.

        Returns:
            CompactionBatch grouped by transition type.
        """
        ...

    @abstractmethod
    async def update_workflow_memory_tier(
        self,
        entry_id: str,
        tier: str,
        output_summary: str | None = None,
        effectiveness_notes: str | None = None,
    ) -> None:
        """Update the tier and optionally compressed fields on a WorkflowMemoryEntry.

        Args:
            entry_id: The entry's id field.
            tier: New tier value ("warm" or "cold").
            output_summary: Replacement text (None = leave unchanged).
            effectiveness_notes: Replacement text (None = leave unchanged).
        """
        ...

    @abstractmethod
    async def update_conceptual_memory_tier(
        self,
        entry_id: str,
        tier: str,
        recommended_workflows: list[dict] | None = None,
        anti_patterns: str | None = None,
    ) -> None:
        """Update the tier and optionally trimmed fields on a ConceptualMemoryEntry.

        Args:
            entry_id: The entry's id field.
            tier: New tier value ("warm" or "cold").
            recommended_workflows: Replacement list (None = leave unchanged).
            anti_patterns: Replacement text (None = leave unchanged).
        """
        ...


class MetricsStore(ABC):
    """Abstract interface for workflow metrics storage.

    Tracks workflow runs and task executions for performance analysis.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the metrics store."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the metrics store and release resources."""
        ...

    # =========================================================================
    # Workflow Run Operations
    # =========================================================================

    @abstractmethod
    async def record_run(self, run: WorkflowRun) -> None:
        """Record a workflow run (insert or update)."""
        ...

    @abstractmethod
    async def update_rating(self, run_id: str, rating: int) -> None:
        """Update the user rating for a run (1-5)."""
        ...

    @abstractmethod
    async def get_run(self, run_id: str) -> WorkflowRun | None:
        """Get a specific run by ID."""
        ...

    @abstractmethod
    async def get_stats(self, workflow_name: str) -> WorkflowStats:
        """Get aggregated stats for a workflow."""
        ...

    @abstractmethod
    async def get_all_stats(self) -> list[WorkflowStats]:
        """Get stats for all workflows, ordered by total runs descending."""
        ...

    @abstractmethod
    async def get_recent_runs(self, limit: int = 10) -> list[WorkflowRun]:
        """Get the most recent workflow runs."""
        ...

    @abstractmethod
    async def get_runs_since(self, cutoff: datetime, limit: int = 500) -> list[WorkflowRun]:
        """Get all workflow runs since the cutoff datetime, newest first.

        Args:
            cutoff: Only include runs with started_at >= cutoff.
            limit: Maximum number of runs to return.

        Returns:
            List of WorkflowRun objects, ordered by started_at descending.
        """
        ...

    @abstractmethod
    async def get_runs_for_workflow(self, workflow_name: str, limit: int = 10) -> list[WorkflowRun]:
        """Get recent runs for a specific workflow."""
        ...

    @abstractmethod
    async def get_total_cost_since(self, since: datetime) -> float:
        """Return the total USD cost of all runs completed since *since*.

        Used by BudgetManager to calculate daily spend.
        """
        ...

    # =========================================================================
    # Task Execution Operations
    # =========================================================================

    @abstractmethod
    async def record_task_execution(self, execution: TaskExecution) -> None:
        """Record a task execution."""
        ...

    @abstractmethod
    async def record_task_executions(self, executions: list[TaskExecution]) -> None:
        """Record multiple task executions in batch."""
        ...

    @abstractmethod
    async def get_task_executions(self, run_id: str) -> list[TaskExecution]:
        """Get all task executions for a workflow run, ordered by execution_order."""
        ...


class ProfileStore(ABC):
    """Abstract interface for the per-user values-profile store.

    The values profile (REQ-ETH-002 / F18) is identity/preference data, not a
    record of past actions, so it lives in its own store alongside MemoryStore
    and MetricsStore. Each save produces a new immutable ``ValuesProfileVersion``
    with a monotonically increasing ``version_number``; the store retains the
    full history per user and tracks which version is current.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the profile store."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the profile store and release resources."""
        ...

    @abstractmethod
    async def get_current(self, user_id: int) -> ValuesProfileVersion | None:
        """Return the user's current (most recent) values-profile version.

        Returns None if the user has no profile yet.
        """
        ...

    @abstractmethod
    async def get_version(self, version_id: str) -> ValuesProfileVersion | None:
        """Return a specific version by id, or None if not found."""
        ...

    @abstractmethod
    async def save_version(
        self, user_id: int, version: ValuesProfileVersion
    ) -> ValuesProfileVersion:
        """Persist a new version for the user.

        The store assigns ``id``, ``version_number`` (= previous max + 1), and
        ``created_at``. The returned instance has those fields populated.
        Existing versions are never mutated or deleted.
        """
        ...

    @abstractmethod
    async def get_approved_tags(self, field: str) -> list[dict]:
        """Return approved tags (``status in {seeded, promoted}``) for a field.

        Each returned dict has at least ``slug``, ``label``, ``description``.
        Used by ``extract_values_tags`` to anchor the LLM prompt.
        """
        ...

    @abstractmethod
    async def record_confirmed_tags(self, field_to_tags: dict[str, list[dict[str, str]]]) -> None:
        """Record tags that the user confirmed on the wizard's review step.

        For each ``(field, slug)`` pair: upsert a Tag row, incrementing
        ``usage_count``. New tags are created with ``status="candidate"``;
        existing tags retain their current status.

        Args:
            field_to_tags: Mapping of field name to list of ``{slug, label}``
                (and optional ``description``) dicts.
        """
        ...


class PersonalKnowledgeStore(ABC):
    """Abstract interface for the personal knowledge store.

    Stores typed, user-scoped knowledge entries (facts, preferences, relationships,
    routines, skills, history) that persist across sessions and are injected into
    the agent's planning context at the start of each goal.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the store."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the store and release resources."""
        ...

    @abstractmethod
    async def add_entry(self, entry: KnowledgeEntry) -> None:
        """Persist a new knowledge entry."""
        ...

    @abstractmethod
    async def update_entry(self, entry: KnowledgeEntry) -> None:
        """Update an existing knowledge entry."""
        ...

    @abstractmethod
    async def soft_delete_entry(self, entry_id: str) -> bool:
        """Soft-delete a knowledge entry by setting its deleted_at timestamp.

        Deleted entries are excluded from active queries by default but
        retained for audit purposes.

        Returns:
            True if the entry was found and soft-deleted, False if not found.
        """
        ...

    @abstractmethod
    async def get_entry(self, entry_id: str) -> KnowledgeEntry | None:
        """Get a single entry by ID, or None if not found."""
        ...

    @abstractmethod
    async def get_entries(
        self,
        user_id: int,
        category: str | None = None,
        include_deleted: bool = False,
    ) -> list[KnowledgeEntry]:
        """Get all entries for a user, optionally filtered by category.

        Soft-deleted entries are excluded unless include_deleted is True.
        Results are ordered by last_verified descending.
        """
        ...

    @abstractmethod
    async def get_context_for_llm(self, user_id: int, limit: int = 50) -> str:
        """Format knowledge entries as a context string for LLM injection.

        Returns entries formatted as ``[category] key: value``, one per line,
        ordered by last_verified descending. Returns an empty string when no
        entries exist for the user. Excludes soft-deleted entries.
        """
        ...

    @abstractmethod
    async def get_entries_for_verification(
        self,
        user_id: int,
        low_confidence_threshold: float = 0.6,
        max_age_days: int = 90,
        max_entries: int = 5,
    ) -> list[KnowledgeEntry]:
        """Return entries that are candidates for human verification.

        Selects non-deleted entries where confidence < low_confidence_threshold
        OR last_verified is older than max_age_days, ordered by confidence
        ascending (lowest first). Capped at max_entries.
        """
        ...

    @abstractmethod
    async def find_contradicting_entry(
        self, user_id: int, category: str, key: str
    ) -> KnowledgeEntry | None:
        """Return the existing non-deleted entry for (user_id, category, key), or None.

        Used by add_knowledge to detect contradictions before writing.
        """
        ...


class EthicsAuditStore(ABC):
    """Abstract interface for the append-only ethics evaluation audit log.

    Every ethics gate evaluation is written here after the verdict is computed.
    Entries are immutable once written — no update or delete operations exist.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the store."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the store and release resources."""
        ...

    @abstractmethod
    async def append(self, entry: EthicsAuditEntry) -> None:
        """Append an audit entry to the log.

        Args:
            entry: The ethics evaluation result to persist.
        """
        ...

    @abstractmethod
    async def list_entries(
        self,
        approved: bool | None = None,
        process_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EthicsAuditEntry]:
        """Return audit entries, newest first, with optional filters.

        Args:
            approved: Filter by verdict (None = all).
            process_id: Filter by process id (None = all).
            from_date: Include only entries with evaluated_at >= from_date.
            to_date: Include only entries with evaluated_at <= to_date.
            limit: Maximum number of entries to return.
            offset: Number of entries to skip (for pagination).
        """
        ...

    @abstractmethod
    async def get(self, entry_id: str) -> EthicsAuditEntry | None:
        """Return a single entry by id, or None if not found."""
        ...


class TrustStore(ABC):
    """Abstract interface for per-(user, domain) trust levels (REQ-TRUST-001).

    Trust is a policy layer above the engine: gates (F13) read the level
    before executing domain-scoped actions. Every (user, domain) pair reads
    as SUPERVISED until explicitly changed, and each change appends an
    immutable ``TrustChangeRecord`` — there is no update or delete API.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the trust store."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the trust store and release resources."""
        ...

    @abstractmethod
    async def get_trust_level(self, user_id: int, domain: str) -> TrustLevel:
        """Return the trust level for a (user, domain) pair.

        Pairs that have never been set return SUPERVISED without creating
        a stored record.
        """
        ...

    @abstractmethod
    async def set_trust_level(
        self,
        user_id: int,
        domain: str,
        level: TrustLevel,
        reason: str,
        changed_by: str,
    ) -> TrustChangeRecord:
        """Set the trust level for a (user, domain) pair and audit the change.

        Args:
            user_id: The user whose trust is being changed.
            domain: A domain present in the taxonomy registry.
            level: The new trust level.
            reason: Why the level is changing (stored in the audit record).
            changed_by: Who made the change (stored in the audit record).

        Returns:
            The appended TrustChangeRecord.

        Raises:
            ValueError: If the domain is not in the taxonomy registry.
        """
        ...

    @abstractmethod
    async def get_all_trust_levels(self, user_id: int) -> dict[str, TrustLevel]:
        """Return the trust level of every registered domain for a user.

        Domains without a stored level are reported as SUPERVISED.
        """
        ...

    @abstractmethod
    async def list_trust_changes(
        self, user_id: int, domain: str | None = None
    ) -> list[TrustChangeRecord]:
        """Return trust change records for a user, newest first.

        Args:
            user_id: The user whose history to return.
            domain: Restrict to one domain (None = all domains).
        """
        ...


@dataclass
class CredentialKey:
    """Identifies a stored credential without exposing its value."""

    user_id: str
    integration_name: str
    credential_type: str


class CredentialStore(ABC):
    """Abstract interface for OS-keychain-backed credential storage.

    Credentials are indexed by ``(user_id, integration_name, credential_type)``
    and stored in the platform's native secure storage (macOS Keychain,
    Secret Service on Linux, Windows Credential Manager) or a file-based
    fallback with 0600 permissions.

    Credentials MUST NEVER appear in logs, process properties, or exception
    messages.  All implementations must be careful to only pass ``value`` to
    the backend and never include it in any string formatting.
    """

    @abstractmethod
    async def get(
        self,
        user_id: str,
        integration_name: str,
        credential_type: str,
    ) -> str | None:
        """Retrieve a credential value.

        Args:
            user_id: User identifier (namespaces the credential).
            integration_name: Integration name (e.g. ``github``, ``google``).
            credential_type: Credential type (e.g. ``api_key``, ``token``).

        Returns:
            The stored credential value, or None if not found.
        """
        ...

    @abstractmethod
    async def set(
        self,
        user_id: str,
        integration_name: str,
        credential_type: str,
        value: str,
    ) -> None:
        """Store a credential value.

        Args:
            user_id: User identifier.
            integration_name: Integration name.
            credential_type: Credential type.
            value: Credential value — never log this.
        """
        ...

    @abstractmethod
    async def delete(
        self,
        user_id: str,
        integration_name: str,
        credential_type: str,
    ) -> None:
        """Remove a credential.

        Args:
            user_id: User identifier.
            integration_name: Integration name.
            credential_type: Credential type.
        """
        ...

    @abstractmethod
    async def list(self, user_id: str) -> list[CredentialKey]:
        """List all credential keys for a user (no values returned).

        Args:
            user_id: User identifier.

        Returns:
            List of CredentialKey dataclasses (no credential values).
        """
        ...


class InMemoryCredentialStore(CredentialStore):
    """In-memory credential store for testing and standalone CLI use.

    Data is lost on process exit.  Do not use in production — use
    ``KeyringCredentialStore`` or ``FileCredentialStore`` instead.

    The ``_store`` dict is intentionally excluded from ``__repr__`` to
    avoid accidental credential exposure in logs.
    """

    def __init__(self) -> None:
        # Keyed by (user_id, integration_name, credential_type)
        self._store: dict[tuple[str, str, str], str] = {}

    def __repr__(self) -> str:
        return f"InMemoryCredentialStore(entries={len(self._store)})"

    async def get(
        self,
        user_id: str,
        integration_name: str,
        credential_type: str,
    ) -> str | None:
        return self._store.get((user_id, integration_name, credential_type))

    async def set(
        self,
        user_id: str,
        integration_name: str,
        credential_type: str,
        value: str,
    ) -> None:
        self._store[(user_id, integration_name, credential_type)] = value

    async def delete(
        self,
        user_id: str,
        integration_name: str,
        credential_type: str,
    ) -> None:
        self._store.pop((user_id, integration_name, credential_type), None)

    async def list(self, user_id: str) -> list[CredentialKey]:
        return [
            CredentialKey(
                user_id=u,
                integration_name=i,
                credential_type=t,
            )
            for (u, i, t) in self._store
            if u == user_id
        ]

    # ------------------------------------------------------------------
    # Test helpers (not part of the interface)
    # ------------------------------------------------------------------

    def _dump(self) -> dict[tuple[str, str, str], Any]:
        """Return all stored credentials — test use only."""
        return dict(self._store)
