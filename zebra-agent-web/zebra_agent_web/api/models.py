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
    properties = models.TextField(
        blank=True, default="{}", help_text="JSON serialized properties dict"
    )
    parent_process_id = models.CharField(max_length=255, blank=True, null=True)
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


class TaskExecutionModel(models.Model):
    """Record of a single task execution within a workflow run."""

    id = models.CharField(max_length=255, primary_key=True)
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
    concept = models.CharField(max_length=500, db_index=True, help_text="Goal pattern / category")
    recommended_workflows = models.JSONField(
        default=list,
        help_text="List of {name, fit_notes, avg_rating, use_count} dicts",
    )
    anti_patterns = models.TextField(blank=True, default="", help_text="What doesn't work here")
    last_updated = models.DateTimeField(db_index=True)
    tokens = models.IntegerField(default=0)

    class Meta:
        db_table = "zebra_conceptual_memories"
        verbose_name = "Conceptual Memory"
        verbose_name_plural = "Conceptual Memories"
        indexes = [
            models.Index(fields=["-last_updated"]),
        ]

    def __str__(self):
        return f"Concept: {self.concept[:60]}"


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

    class Meta:
        db_table = "zebra_system_state"
        verbose_name = "System State"

    def __str__(self):
        return f"SystemState halted={self.halted}"


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
