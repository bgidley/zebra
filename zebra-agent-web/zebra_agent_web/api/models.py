"""Django models for Zebra workflow engine and agent metrics.

This module provides Django ORM models for:
1. StateStore: ProcessDefinition, ProcessInstance, TaskInstance, FlowOfExecution
2. MetricsStore: WorkflowRun, TaskExecution

Using Django's ORM handles Oracle CLOB fields transparently via TextField.
"""

from django.db import models

# =============================================================================
# StateStore Models (Workflow Engine)
# =============================================================================


class ProcessDefinitionModel(models.Model):
    """Workflow blueprint/definition storage.

    Stores the complete ProcessDefinition as JSON in the data field.
    """

    id = models.CharField(max_length=255, primary_key=True)
    name = models.CharField(max_length=255)
    version = models.IntegerField(default=1)
    data = models.TextField(help_text="JSON serialized ProcessDefinition")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "zebra_process_definitions"
        verbose_name = "Process Definition"
        verbose_name_plural = "Process Definitions"

    def __str__(self):
        return f"{self.name} v{self.version} ({self.id})"


class ProcessInstanceModel(models.Model):
    """Runtime instance of a workflow process."""

    id = models.CharField(max_length=255, primary_key=True)
    definition_id = models.CharField(max_length=255, db_index=True)
    state = models.CharField(max_length=50, db_index=True)
    user_id = models.IntegerField(null=True, blank=True, db_index=True)
    properties = models.TextField(
        blank=True, default="{}", help_text="JSON serialized properties dict"
    )
    parent_process_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    parent_task_id = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "zebra_process_instances"
        verbose_name = "Process Instance"
        verbose_name_plural = "Process Instances"
        indexes = [
            models.Index(fields=["state", "created_at"]),
        ]

    def __str__(self):
        return f"Process {self.id} ({self.state})"


class TaskInstanceModel(models.Model):
    """Runtime instance of a task within a workflow process."""

    id = models.CharField(max_length=255, primary_key=True)
    process_id = models.CharField(max_length=255, db_index=True)
    task_definition_id = models.CharField(max_length=255)
    user_id = models.IntegerField(null=True, blank=True, db_index=True)
    state = models.CharField(max_length=50, db_index=True)
    foe_id = models.CharField(max_length=255, db_index=True)
    properties = models.TextField(
        blank=True, default="{}", help_text="JSON serialized properties dict"
    )
    result = models.TextField(blank=True, null=True, help_text="JSON serialized task result")
    error = models.TextField(blank=True, null=True, help_text="Error message if task failed")
    execution_attempt = models.IntegerField(default=0)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "zebra_task_instances"
        verbose_name = "Task Instance"
        verbose_name_plural = "Task Instances"
        indexes = [
            models.Index(fields=["process_id", "state"]),
        ]

    def __str__(self):
        return f"Task {self.id} ({self.state})"


class FlowOfExecutionModel(models.Model):
    """Tracks a single execution path through the workflow (for parallel branches)."""

    id = models.CharField(max_length=255, primary_key=True)
    process_id = models.CharField(max_length=255, db_index=True)
    parent_foe_id = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField()

    class Meta:
        db_table = "zebra_flows_of_execution"
        verbose_name = "Flow of Execution"
        verbose_name_plural = "Flows of Execution"

    def __str__(self):
        return f"FOE {self.id} (process={self.process_id})"


class ProcessEventModel(models.Model):
    """One step-journal entry for a process (#184). See ``zebra.core.models.ProcessEvent``."""

    id = models.CharField(max_length=36, primary_key=True)
    process_id = models.CharField(max_length=255)
    kind = models.CharField(max_length=32)
    task_instance_id = models.CharField(max_length=255, blank=True, null=True)
    task_definition_id = models.CharField(max_length=255, blank=True, null=True)
    attempt = models.IntegerField(default=0)
    occurred_at = models.DateTimeField()
    changed = models.TextField(blank=True, default="{}", help_text="JSON properties changed")
    removed = models.TextField(blank=True, default="[]", help_text="JSON property keys removed")
    error = models.TextField(blank=True, null=True)
    next_route = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = "zebra_process_events"
        verbose_name = "Process Event"
        verbose_name_plural = "Process Events"
        indexes = [
            models.Index(fields=["process_id", "occurred_at"], name="zebra_pevt_proc_ts_idx"),
        ]

    def __str__(self):
        return f"{self.kind} on {self.process_id}"


class ProcessLockModel(models.Model):
    """Distributed lock for process instances to handle concurrent access."""

    process_id = models.CharField(max_length=255, primary_key=True)
    owner = models.CharField(max_length=255)
    acquired_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "zebra_process_locks"
        verbose_name = "Process Lock"
        verbose_name_plural = "Process Locks"

    def __str__(self):
        return f"Lock on {self.process_id} by {self.owner}"


# =============================================================================
# MetricsStore Models (Agent Tracking)
# =============================================================================


class WorkflowRunModel(models.Model):
    """Record of a single workflow execution by the agent."""

    id = models.CharField(max_length=255, primary_key=True)
    workflow_name = models.CharField(max_length=255, db_index=True)
    user_id = models.IntegerField(null=True, blank=True, db_index=True)
    goal = models.TextField(help_text="User's goal/request")
    started_at = models.DateTimeField(db_index=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    success = models.BooleanField(default=False)
    user_rating = models.IntegerField(blank=True, null=True, help_text="1-5 rating")
    tokens_used = models.IntegerField(default=0)
    input_tokens = models.IntegerField(default=0, help_text="Input (prompt) tokens used")
    output_tokens = models.IntegerField(default=0, help_text="Output (completion) tokens used")
    cost = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0,
        help_text="USD cost of this run",
    )
    error = models.TextField(blank=True, null=True, help_text="Error message if failed")
    output = models.TextField(blank=True, null=True, help_text="Workflow output/result")
    model = models.CharField(
        max_length=255, blank=True, default="", help_text="LLM model used for this run"
    )
    extends_run_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="Run this one follows up on (F116)",
    )
    continuation_comment = models.TextField(
        blank=True, null=True, help_text="User's progress comment when continuing a run (F134)"
    )
    continuation_decision = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="same_workflow | existing_workflow | new_workflow (F135)",
    )
    continuation_rationale = models.TextField(
        blank=True, null=True, help_text="Why the continuation route was chosen (F135)"
    )

    class Meta:
        db_table = "zebra_workflow_runs"
        verbose_name = "Workflow Run"
        verbose_name_plural = "Workflow Runs"
        indexes = [
            models.Index(fields=["-started_at"]),
        ]

    def __str__(self):
        status = "success" if self.success else "failed"
        return f"{self.workflow_name} ({status}) - {self.started_at}"


class LLMSpendModel(models.Model):
    """One LLM call's spend: the ledger the daily budget sums (#206)."""

    occurred_at = models.DateTimeField(db_index=True)
    cost = models.DecimalField(max_digits=12, decimal_places=8, default=0)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    model = models.CharField(max_length=255, blank=True, default="")
    process_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    class Meta:
        db_table = "zebra_llm_spend"
        verbose_name = "LLM Spend"
        verbose_name_plural = "LLM Spend"

    def __str__(self):
        return f"${self.cost} {self.model} at {self.occurred_at}"


class TaskExecutionModel(models.Model):
    """Record of a single task execution within a workflow run."""

    id = models.CharField(max_length=255, primary_key=True)
    user_id = models.IntegerField(null=True, blank=True, db_index=True)
    run = models.ForeignKey(
        WorkflowRunModel,
        on_delete=models.CASCADE,
        related_name="task_executions",
        db_column="run_id",
    )
    task_definition_id = models.CharField(max_length=255)
    task_name = models.CharField(max_length=255)
    execution_order = models.IntegerField()
    state = models.CharField(max_length=50)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(blank=True, null=True)
    output = models.TextField(blank=True, null=True, help_text="Task output/result")
    error = models.TextField(blank=True, null=True, help_text="Error message if failed")

    class Meta:
        db_table = "zebra_task_executions"
        verbose_name = "Task Execution"
        verbose_name_plural = "Task Executions"
        indexes = [
            models.Index(fields=["run", "execution_order"]),
        ]

    def __str__(self):
        return f"{self.task_name} ({self.state}) - order {self.execution_order}"


# =============================================================================
# MemoryStore Models (Agent Memory - Workflow-focused two-tier system)
# =============================================================================


class WorkflowMemoryModel(models.Model):
    """Detailed record of a single workflow run's behaviour and effectiveness."""

    id = models.CharField(max_length=255, primary_key=True)
    user_id = models.IntegerField(null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    workflow_name = models.CharField(max_length=255, db_index=True)
    goal = models.TextField(help_text="User's goal/request")
    success = models.BooleanField(default=False)
    input_summary = models.TextField(help_text="What went into the workflow")
    output_summary = models.TextField(help_text="What came out of the workflow")
    effectiveness_notes = models.TextField(
        blank=True, default="", help_text="LLM assessment of what worked / didn't"
    )
    tokens_used = models.IntegerField(default=0)
    rating = models.IntegerField(blank=True, null=True, help_text="User rating 1-5")
    user_feedback = models.TextField(
        blank=True, default="", help_text="Free-text user feedback for next run"
    )
    run_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Link to the workflow run for post-hoc updates",
    )
    model = models.CharField(
        max_length=255, blank=True, default="", help_text="LLM model used for this run"
    )
    tier = models.CharField(
        max_length=10, default="hot", help_text="Compaction tier: hot | warm | cold"
    )

    class Meta:
        db_table = "zebra_workflow_memories"
        verbose_name = "Workflow Memory"
        verbose_name_plural = "Workflow Memories"
        indexes = [
            models.Index(fields=["-timestamp"]),
            models.Index(fields=["workflow_name", "-timestamp"]),
        ]

    def __str__(self):
        status = "success" if self.success else "failed"
        return f"{self.workflow_name} ({status}) - {self.timestamp}"


class ConceptualMemoryModel(models.Model):
    """Compact index entry mapping a goal pattern to recommended workflows."""

    id = models.CharField(max_length=255, primary_key=True)
    user_id = models.IntegerField(null=True, blank=True, db_index=True)
    concept = models.CharField(max_length=500, db_index=True, help_text="Goal pattern / category")
    recommended_workflows = models.JSONField(
        default=list,
        help_text="List of {name, fit_notes, avg_rating, use_count} dicts",
    )
    anti_patterns = models.TextField(blank=True, default="", help_text="What doesn't work here")
    last_updated = models.DateTimeField(db_index=True)
    tokens = models.IntegerField(default=0)
    tier = models.CharField(
        max_length=10, default="hot", help_text="Compaction tier: hot | warm | cold"
    )

    class Meta:
        db_table = "zebra_conceptual_memories"
        verbose_name = "Conceptual Memory"
        verbose_name_plural = "Conceptual Memories"
        indexes = [
            models.Index(fields=["-last_updated"]),
        ]

    def __str__(self):
        return f"Concept: {self.concept[:60]}"


class PostmortemModel(models.Model):
    """A lesson learned from a failed, timed-out or badly rated run (#175)."""

    id = models.CharField(max_length=255, primary_key=True)
    user_id = models.IntegerField(null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    # One postmortem per run, even if two triggers race (#175). No run is NULL, not "":
    # Oracle reads "" as NULL and has no conditional unique constraints (W036), and
    # every backend allows many NULLs under a plain unique constraint.
    run_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    goal = models.TextField()
    workflow_name = models.CharField(max_length=255, blank=True, default="")
    trigger = models.CharField(max_length=20, help_text="failure | timeout | low_rating")
    what_happened = models.TextField(blank=True, default="")
    root_cause = models.TextField(blank=True, default="")
    lesson = models.TextField()
    voice = models.TextField(blank=True, null=True)
    confidence = models.FloatField(blank=True, null=True)

    class Meta:
        db_table = "zebra_postmortems"
        verbose_name = "Postmortem"
        verbose_name_plural = "Postmortems"
        indexes = [
            models.Index(fields=["-timestamp"]),
        ]

    def __str__(self):
        return f"Postmortem ({self.trigger}): {self.goal[:60]}"


class GymScoreModel(models.Model):
    """One golden task scored against one version of a workflow (#171).

    System-level, like Dream Cycles: not scoped to a user.
    """

    id = models.CharField(max_length=255, primary_key=True)
    gym_run_id = models.CharField(max_length=255, db_index=True)
    golden_id = models.CharField(max_length=255, db_index=True)
    workflow_name = models.CharField(max_length=255, db_index=True)
    variant = models.CharField(max_length=20, help_text="current | candidate")
    score = models.FloatField(null=True, blank=True)
    error = models.TextField(blank=True, null=True)
    details = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "zebra_gym_scores"
        verbose_name = "Gym score"
        verbose_name_plural = "Gym scores"
        indexes = [
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"Gym {self.golden_id} [{self.variant}]: {self.score}"


# =============================================================================
# System State (Kill Switch)
# =============================================================================


class SystemStateModel(models.Model):
    """Singleton system-wide state record (always pk=1).

    Use SystemStateModel.objects.get_or_create(pk=1) to access.
    """

    halted = models.BooleanField(default=False)
    halted_at = models.DateTimeField(null=True, blank=True)
    halted_reason = models.CharField(max_length=500, blank=True, default="")

    # Single-user identity (F4)
    user_display_name = models.CharField(max_length=255, blank=True, default="")
    user_identity_id = models.CharField(max_length=255, blank=True, default="")
    setup_completed = models.BooleanField(default=False)

    # Zebra Commons identity (S1, #228). Public keys only: secrets live in the
    # credential store (commons-zebra / commons-device).
    zebra_pubkey = models.CharField(max_length=64, blank=True, default="")
    zebra_display_name = models.CharField(max_length=255, blank=True, default="")
    device_pubkey = models.CharField(max_length=64, blank=True, default="")
    device_label = models.CharField(max_length=100, blank=True, default="")
    sphere = models.CharField(max_length=40, blank=True, default="")
    sphere_observed = models.BooleanField(default=False)
    sync_direction = models.CharField(
        max_length=10, default="both", help_text="send / receive / both / off (S3b)"
    )
    commons_owner_user_id = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "zebra_system_state"
        verbose_name = "System State"

    def __str__(self):
        return f"SystemState halted={self.halted} user={self.user_display_name!r}"


class CommonsDeviceModel(models.Model):
    """A device certified (or revoked) by a Zebra key, with the signed events (#228).

    One row per (Zebra key, device key). ``cert_event`` is the latest ``DEVICE_CERT``
    and ``revoke_event`` the ``DEVICE_REVOKE``, both as NIP-01 JSON, so the chain can
    be re-verified at any time. Label, sphere and observed mirror the cert for listing.
    """

    zebra_pubkey = models.CharField(max_length=64, db_index=True)
    device_pubkey = models.CharField(max_length=64, db_index=True)
    label = models.CharField(max_length=100)
    sphere = models.CharField(max_length=40)
    observed = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    cert_event = models.JSONField()
    revoke_event = models.JSONField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    user_id = models.IntegerField(null=True, blank=True, help_text="Commons owner")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "zebra_commons_devices"
        verbose_name = "Commons device"
        verbose_name_plural = "Commons devices"
        constraints = [
            models.UniqueConstraint(
                fields=["zebra_pubkey", "device_pubkey"],
                name="zebra_commons_device_unique",
            ),
        ]

    def __str__(self):
        return f"CommonsDevice({self.label}, {self.sphere})"


class AppendOnlyError(RuntimeError):
    """A Commons mirror row may not be changed or deleted (#231)."""


class _AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise AppendOnlyError("the Commons event mirror is append-only")

    def delete(self):
        raise AppendOnlyError("the Commons event mirror is append-only")


class CommonsEventModel(models.Model):
    """The local mirror: one row per Commons event this Zebra publishes or relies on (#231).

    Append-only: saving an existing row, ``update()`` and ``delete()`` raise
    ``AppendOnlyError``. ``event`` is the full NIP-01 JSON (re-verifiable); ``content`` is its
    content parsed as JSON (or ``{"text": ...}``). ``relay_seq`` is the canonical relay's
    receipt ``seq`` when it was known at insert (receipts are rows of their own).
    ``user_id`` is the Commons owner (REQ-USR-002: Commons state is per instance).
    """

    event_id = models.CharField(max_length=64, unique=True)
    kind = models.IntegerField(db_index=True)
    pubkey = models.CharField(max_length=64, db_index=True)
    created_at = models.BigIntegerField(help_text="The event's created_at (Unix seconds)")
    relay_seq = models.BigIntegerField(null=True, blank=True)
    content = models.JSONField()
    sig = models.CharField(max_length=128)
    event = models.JSONField()
    user_id = models.IntegerField(null=True, blank=True, db_index=True, help_text="Commons owner")
    stored_at = models.DateTimeField(auto_now_add=True)

    objects = _AppendOnlyQuerySet.as_manager()

    class Meta:
        db_table = "zebra_commons_events"
        verbose_name = "Commons event"
        verbose_name_plural = "Commons events"
        ordering = ["id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError("the Commons event mirror is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("the Commons event mirror is append-only")

    def __str__(self):
        return f"CommonsEvent({self.kind}, {self.event_id[:12]})"


class WorkflowOfferModel(models.Model):
    """One public ``OFFER`` this Zebra has seen, per content hash (#232, S5).

    Written only by ``DjangoOfferStore`` (``zebra_agent.commons.offers.OfferStore``), which
    enforces the status table. ``judgement`` is this Zebra's local verdict (stage, label,
    voice, the gate's recorded reason, process id); it is never published. ``user_id`` is
    the Commons owner (REQ-USR-002: Commons state is per instance).
    """

    STATUS_CHOICES = [
        ("seen", "Seen"),
        ("judging", "Judging"),
        ("adopted", "Adopted"),
        ("rejected", "Rejected"),
        ("delisted", "Delisted"),
    ]

    content_sha256 = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    summary = models.TextField(blank=True, default="")
    use_when = models.TextField(blank=True, default="")
    stats = models.JSONField(default=dict)
    publisher_pubkey = models.CharField(max_length=64, db_index=True)
    event_id = models.CharField(max_length=64)
    offered_at = models.BigIntegerField(default=0, help_text="The OFFER's created_at")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="seen", db_index=True)
    judgement = models.JSONField(default=dict, blank=True)
    user_id = models.IntegerField(null=True, blank=True, db_index=True, help_text="Commons owner")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "zebra_workflow_offers"
        verbose_name = "Commons workflow offer"
        ordering = ["-offered_at"]

    def __str__(self):
        return f"WorkflowOffer({self.name!r}, {self.status})"


class PeerModel(models.Model):
    """A Zebra this Zebra knows of, in its web of trust (#233, S6).

    Written only by ``DjangoPeerTrustStore`` (``zebra_agent.commons.peers.TrustStore``).
    ``vouched_by_user`` and ``owner_weight`` are the owner's (never an LLM's); ``local_trust`` and
    ``best_path`` are computed by ``trust.compute_trust``. ``user_id`` is the Commons owner.
    """

    pubkey = models.CharField(max_length=64, unique=True)
    display_name = models.CharField(max_length=80, blank=True, default="")
    vouched_by_user = models.BooleanField(default=False)
    owner_weight = models.FloatField(null=True, blank=True)
    local_trust = models.FloatField(default=0.0)
    best_path = models.JSONField(default=dict, blank=True)
    last_seen = models.BigIntegerField(default=0, help_text="Newest event seen from it (Unix)")
    user_id = models.IntegerField(null=True, blank=True, db_index=True, help_text="Commons owner")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "zebra_commons_peers"
        verbose_name = "Commons peer"
        ordering = ["-local_trust", "pubkey"]

    def __str__(self):
        return f"Peer({self.pubkey[:12]}, {self.local_trust:.2f})"


class TrustEdgeModel(models.Model):
    """The latest trust edge per ``(from_pubkey, to_pubkey)`` (#233, S6).

    From a verified ``TRUST`` event (``event_id``), or this Zebra's own edge
    (``published_weight``: the weight last published; ``event_id`` empty until published;
    ``pending``: an owner change the relay has not yet accepted).
    Written only by ``DjangoPeerTrustStore``; ``user_id`` is the Commons owner.
    """

    from_pubkey = models.CharField(max_length=64, db_index=True)
    to_pubkey = models.CharField(max_length=64, db_index=True)
    weight = models.FloatField()
    reason = models.CharField(max_length=160)
    event_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.BigIntegerField(default=0, help_text="The event's created_at (Unix)")
    relay_seq = models.BigIntegerField(null=True, blank=True)
    published_weight = models.FloatField(null=True, blank=True)
    pending = models.BooleanField(
        default=False, help_text="Own edge: an owner change not yet published (always retried)"
    )
    user_id = models.IntegerField(null=True, blank=True, db_index=True, help_text="Commons owner")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "zebra_commons_trust_edges"
        verbose_name = "Commons trust edge"
        ordering = ["from_pubkey", "to_pubkey"]
        constraints = [
            models.UniqueConstraint(fields=["from_pubkey", "to_pubkey"], name="uniq_trust_edge")
        ]

    def __str__(self):
        return f"TrustEdge({self.from_pubkey[:8]}→{self.to_pubkey[:8]}, {self.weight:+.2f})"


# =============================================================================
# ProfileStore Models (Values Profile - F18 / REQ-ETH-002)
# =============================================================================


class ValuesProfileModel(models.Model):
    """Per-user pointer to the current values-profile version.

    Exactly one row per user. ``current_version`` is null until the user
    completes the wizard for the first time.
    """

    id = models.CharField(max_length=255, primary_key=True)
    user_id = models.IntegerField(unique=True)
    current_version = models.ForeignKey(
        "api.ValuesProfileVersionModel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "zebra_values_profiles"
        verbose_name = "Values Profile"
        verbose_name_plural = "Values Profiles"

    def __str__(self):
        return f"ValuesProfile(user_id={self.user_id})"


class ValuesProfileVersionModel(models.Model):
    """Immutable snapshot of a values profile.

    Each save creates a new row with monotonically increasing
    ``version_number`` per parent profile. Rows are never mutated or deleted.
    """

    id = models.CharField(max_length=255, primary_key=True)
    profile = models.ForeignKey(
        ValuesProfileModel,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version_number = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_via = models.CharField(max_length=20, default="wizard")

    core_values_text = models.TextField(blank=True, default="")
    core_values_tags = models.JSONField(default=list)
    ethical_positions_text = models.TextField(blank=True, default="")
    ethical_positions_tags = models.JSONField(default=list)
    priorities_text = models.TextField(blank=True, default="")
    priorities_tags = models.JSONField(default=list)
    deal_breakers_text = models.TextField(blank=True, default="")
    deal_breakers_tags = models.JSONField(default=list)

    tags_extracted_at = models.DateTimeField(blank=True, null=True)
    tags_extraction_model = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = "zebra_values_profile_versions"
        verbose_name = "Values Profile Version"
        verbose_name_plural = "Values Profile Versions"
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "version_number"],
                name="zebra_vpv_profile_version_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["profile", "-version_number"]),
        ]

    def __str__(self):
        return f"ValuesProfileVersion(profile={self.profile_id}, v={self.version_number})"


class ValuesTagModel(models.Model):
    """A field-scoped values-taxonomy tag.

    The hybrid taxonomy supports learning over time via the candidate→promoted
    lifecycle. ``seeded`` tags come from the bootstrap fixture; ``candidate``
    tags are accumulated as users confirm new tags in the wizard's review
    step; ``promoted`` tags have been curated up to first-class status.
    Curators may also mark tags ``rejected`` or ``merged`` (into the tag named
    by ``merged_into``) — see ``zebra_agent_web.values_taxonomy`` (#106).
    """

    FIELD_CHOICES = [
        ("core_values", "Core values"),
        ("ethical_positions", "Ethical positions"),
        ("priorities", "Priorities"),
        ("deal_breakers", "Deal-breakers"),
    ]
    STATUS_CHOICES = [
        ("seeded", "Seeded"),
        ("promoted", "Promoted"),
        ("candidate", "Candidate"),
        ("rejected", "Rejected"),
        ("merged", "Merged"),
    ]

    id = models.CharField(max_length=255, primary_key=True)
    field = models.CharField(max_length=50, choices=FIELD_CHOICES, db_index=True)
    slug = models.CharField(max_length=100)
    label = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="candidate")
    usage_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    promoted_at = models.DateTimeField(blank=True, null=True)
    merged_into = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = "zebra_values_tags"
        verbose_name = "Values Tag"
        verbose_name_plural = "Values Tags"
        constraints = [
            models.UniqueConstraint(
                fields=["field", "slug"],
                name="zebra_values_tag_field_slug_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["field", "status"]),
            models.Index(fields=["status", "-usage_count"]),
        ]

    def __str__(self):
        return f"{self.field}:{self.slug} ({self.status})"


# =============================================================================
# WebAuthn (Passkeys)
# =============================================================================


class WebAuthnCredential(models.Model):
    """Stores a WebAuthn credential (passkey) for a Django user."""

    user = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="webauthn_credentials",
    )
    # Store credential ID as a base64url-encoded string (Oracle doesn't allow UNIQUE on BLOB)
    credential_id = models.CharField(max_length=1500, db_index=True, unique=True)
    public_key = models.BinaryField()
    sign_count = models.PositiveIntegerField(default=0)
    transports = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "zebra_webauthn_credentials"

    def __str__(self):
        return f"Credential for {self.user.username}"


# =============================================================================
# Scheduler Models (Polling Scheduler - F27 / REQ-PRIN-008)
# =============================================================================


class RoutineRunModel(models.Model):
    """Persisted last/next run state for each scheduled routine.

    One row per routine name. Updated atomically after every dispatch.
    """

    routine_name = models.CharField(max_length=255, primary_key=True)
    last_run = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField()
    last_status = models.CharField(max_length=50, default="pending")

    class Meta:
        db_table = "zebra_routine_runs"
        verbose_name = "Routine Run"
        verbose_name_plural = "Routine Runs"

    def __str__(self):
        return f"RoutineRun({self.routine_name}, next={self.next_run})"


# =============================================================================
# Personal Knowledge Store (REQ-MEM-004 / F31)
# =============================================================================

KNOWLEDGE_CATEGORY_CHOICES = [
    ("preferences", "Preferences"),
    ("facts", "Facts"),
    ("relationships", "Relationships"),
    ("routines", "Routines"),
    ("skills", "Skills"),
    ("history", "History"),
    ("world", "World"),
]


class KnowledgeEntryModel(models.Model):
    """A typed, user-scoped personal knowledge entry.

    Stores facts, preferences, and structured knowledge about the user that
    the agent reads during planning (REQ-MEM-004).
    """

    id = models.CharField(max_length=36, primary_key=True)
    user_id = models.BigIntegerField(db_index=True)
    category = models.CharField(max_length=50, choices=KNOWLEDGE_CATEGORY_CHOICES, db_index=True)
    key = models.CharField(max_length=255)
    value = models.TextField()
    source = models.CharField(max_length=50, default="human")
    confidence = models.FloatField(default=1.0)
    last_verified = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    time_sensitive = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True, default=None)

    class Meta:
        db_table = "zebra_knowledge_entries"
        verbose_name = "Knowledge Entry"
        verbose_name_plural = "Knowledge Entries"
        indexes = [
            models.Index(fields=["user_id", "category"], name="zebra_know_user_cat_idx"),
        ]

    def __str__(self):
        return f"[{self.category}] {self.key} (user={self.user_id})"


# =============================================================================
# Ethics Audit Log (REQ-ETH-006 / F20)
# =============================================================================


class EthicsAuditEntryModel(models.Model):
    """Immutable record of a single ethics gate evaluation.

    Rows are append-only. save() and delete() raise NotImplementedError on
    existing rows so immutability is enforced at the ORM layer.
    """

    id = models.CharField(max_length=36, primary_key=True)
    process_id = models.CharField(max_length=255, db_index=True)
    goal = models.TextField(help_text="First 500 chars of the evaluated goal")
    approved = models.BooleanField(db_index=True)
    overall_reasoning = models.TextField()
    check_type = models.CharField(max_length=50, help_text="'kantian' or 'kantian+values'")
    user_id = models.IntegerField(null=True, blank=True, db_index=True)
    evaluated_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "ethics_audit_entry"
        verbose_name = "Ethics Audit Entry"
        verbose_name_plural = "Ethics Audit Entries"
        indexes = [
            models.Index(fields=["-evaluated_at"]),
            models.Index(fields=["approved", "-evaluated_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk and EthicsAuditEntryModel.objects.filter(pk=self.pk).exists():
            raise NotImplementedError("EthicsAuditEntryModel rows are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise NotImplementedError("EthicsAuditEntryModel rows are immutable")

    def __str__(self):
        verdict = "approved" if self.approved else "rejected"
        return f"EthicsAudit({verdict}, {self.evaluated_at.date()})"


# =============================================================================
# Trust Levels (REQ-TRUST-001 / F12)
# =============================================================================


class TrustLevelModel(models.Model):
    """Current trust level for a (user, domain) pair.

    Rows exist only for pairs that have been explicitly set — unset pairs
    read as SUPERVISED in the store layer without a row here.
    """

    user_id = models.IntegerField(db_index=True)
    domain = models.CharField(max_length=100)
    level = models.CharField(max_length=20, default="SUPERVISED")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "zebra_trust_levels"
        verbose_name = "Trust Level"
        verbose_name_plural = "Trust Levels"
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "domain"],
                name="zebra_trust_user_domain_unique",
            ),
        ]

    def __str__(self):
        return f"TrustLevel(user={self.user_id}, {self.domain}={self.level})"


class TrustChangeModel(models.Model):
    """Immutable audit record of a single trust level change.

    Rows are append-only. save() and delete() raise NotImplementedError on
    existing rows so immutability is enforced at the ORM layer.
    """

    id = models.CharField(max_length=36, primary_key=True)
    user_id = models.IntegerField(db_index=True)
    domain = models.CharField(max_length=100, db_index=True)
    old_level = models.CharField(max_length=20)
    new_level = models.CharField(max_length=20)
    reason = models.TextField()
    changed_by = models.CharField(max_length=255)
    changed_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "zebra_trust_changes"
        verbose_name = "Trust Change"
        verbose_name_plural = "Trust Changes"
        indexes = [
            models.Index(fields=["user_id", "domain", "-changed_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk and TrustChangeModel.objects.filter(pk=self.pk).exists():
            raise NotImplementedError("TrustChangeModel rows are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise NotImplementedError("TrustChangeModel rows are immutable")

    def __str__(self):
        return f"TrustChange({self.domain}: {self.old_level}->{self.new_level})"


class TrustSuggestionModel(models.Model):
    """An agent-submitted trust promotion suggestion awaiting human resolution.

    Suggestions never change a trust level by themselves (REQ-TRUST-004) —
    approval happens through DjangoTrustStore.resolve_suggestion, which records
    the resolving human in the trust change audit trail.
    """

    id = models.CharField(max_length=36, primary_key=True)
    user_id = models.IntegerField(db_index=True)
    domain = models.CharField(max_length=100)
    to_level = models.CharField(max_length=20)
    evidence = models.TextField()
    status = models.CharField(max_length=10, default="pending", db_index=True)
    created_at = models.DateTimeField(db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "zebra_trust_suggestions"
        verbose_name = "Trust Suggestion"
        verbose_name_plural = "Trust Suggestions"
        indexes = [
            models.Index(fields=["user_id", "status", "-created_at"]),
        ]

    def __str__(self):
        return f"TrustSuggestion({self.domain}->{self.to_level}, {self.status})"


class TrustFreedModel(models.Model):
    """Freeing lifecycle state per user (F17 / REQ-TRUST-006).

    One row per user once freeing is initiated. ``freed`` becomes True
    permanently on confirmation; the row is deleted only when a *pending*
    (not-yet-freed) request is cancelled.
    """

    user_id = models.IntegerField(primary_key=True)
    initiated_at = models.DateTimeField()
    initiated_by = models.CharField(max_length=255)
    freed = models.BooleanField(default=False)
    freed_at = models.DateTimeField(null=True, blank=True)
    freed_by = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "zebra_trust_freed"
        verbose_name = "Trust Freed State"
        verbose_name_plural = "Trust Freed States"

    def __str__(self):
        return f"TrustFreed(user={self.user_id}, freed={self.freed})"
