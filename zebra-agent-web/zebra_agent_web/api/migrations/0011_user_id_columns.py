"""Add user_id column to all user-scoped models.

Backfills from process properties __user_id__ where available; falls back
to the first User in the database (single-user deployment assumption).
"""

import json

from django.db import migrations, models


def backfill_process_user_ids(apps, schema_editor):
    """Stamp user_id on ProcessInstanceModel rows from process properties."""
    ProcessInstanceModel = apps.get_model("api", "ProcessInstanceModel")
    User = apps.get_model("auth", "User")

    first_user = User.objects.order_by("id").first()
    fallback_id = first_user.id if first_user else None

    for process in ProcessInstanceModel.objects.filter(user_id__isnull=True):
        try:
            props = json.loads(process.properties or "{}")
            uid = props.get("__user_id__")
        except (json.JSONDecodeError, TypeError):
            uid = None
        process.user_id = uid if uid is not None else fallback_id
        process.save(update_fields=["user_id"])


def backfill_task_user_ids(apps, schema_editor):
    """Stamp user_id on TaskInstanceModel from parent process."""
    TaskInstanceModel = apps.get_model("api", "TaskInstanceModel")
    ProcessInstanceModel = apps.get_model("api", "ProcessInstanceModel")

    process_user_map = {
        p.id: p.user_id for p in ProcessInstanceModel.objects.exclude(user_id__isnull=True)
    }

    for task in TaskInstanceModel.objects.filter(user_id__isnull=True):
        task.user_id = process_user_map.get(task.process_id)
        task.save(update_fields=["user_id"])


def backfill_run_user_ids(apps, schema_editor):
    """Stamp user_id on WorkflowRunModel / TaskExecutionModel from run properties.

    WorkflowRunModel has no direct process link, so we look up the process
    by its run_id property and copy user_id from there.
    """
    WorkflowRunModel = apps.get_model("api", "WorkflowRunModel")
    TaskExecutionModel = apps.get_model("api", "TaskExecutionModel")
    ProcessInstanceModel = apps.get_model("api", "ProcessInstanceModel")
    User = apps.get_model("auth", "User")

    first_user = User.objects.order_by("id").first()
    fallback_id = first_user.id if first_user else None

    # Build run_id -> user_id map from process properties
    run_to_user: dict[str, int | None] = {}
    for process in ProcessInstanceModel.objects.exclude(user_id__isnull=True):
        try:
            props = json.loads(process.properties or "{}")
            run_id = props.get("run_id")
        except (json.JSONDecodeError, TypeError):
            run_id = None
        if run_id:
            run_to_user[run_id] = process.user_id

    for run in WorkflowRunModel.objects.filter(user_id__isnull=True):
        run.user_id = run_to_user.get(run.id, fallback_id)
        run.save(update_fields=["user_id"])

    # TaskExecution inherits from its run
    run_model_user_map = {r.id: r.user_id for r in WorkflowRunModel.objects.all()}
    for exec in TaskExecutionModel.objects.filter(user_id__isnull=True):
        exec.user_id = run_model_user_map.get(exec.run_id)
        exec.save(update_fields=["user_id"])


def backfill_memory_user_ids(apps, schema_editor):
    """Stamp user_id on WorkflowMemoryModel / ConceptualMemoryModel."""
    WorkflowMemoryModel = apps.get_model("api", "WorkflowMemoryModel")
    ConceptualMemoryModel = apps.get_model("api", "ConceptualMemoryModel")
    WorkflowRunModel = apps.get_model("api", "WorkflowRunModel")
    User = apps.get_model("auth", "User")

    first_user = User.objects.order_by("id").first()
    fallback_id = first_user.id if first_user else None

    # WorkflowMemory has a run_id column
    run_to_user = {r.id: r.user_id for r in WorkflowRunModel.objects.exclude(user_id__isnull=True)}

    for mem in WorkflowMemoryModel.objects.filter(user_id__isnull=True):
        mem.user_id = run_to_user.get(mem.run_id, fallback_id)
        mem.save(update_fields=["user_id"])

    # ConceptualMemory is global knowledge — assign to first user (single-user)
    ConceptualMemoryModel.objects.filter(user_id__isnull=True).update(user_id=fallback_id)


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0010_merge_0009_identity_0009_webauthncredential"),
    ]

    operations = [
        # ProcessInstanceModel
        migrations.AddField(
            model_name="processinstancemodel",
            name="user_id",
            field=models.IntegerField(null=True, blank=True, db_index=True),
        ),
        # TaskInstanceModel
        migrations.AddField(
            model_name="taskinstancemodel",
            name="user_id",
            field=models.IntegerField(null=True, blank=True, db_index=True),
        ),
        # WorkflowRunModel
        migrations.AddField(
            model_name="workflowrunmodel",
            name="user_id",
            field=models.IntegerField(null=True, blank=True, db_index=True),
        ),
        # TaskExecutionModel
        migrations.AddField(
            model_name="taskexecutionmodel",
            name="user_id",
            field=models.IntegerField(null=True, blank=True, db_index=True),
        ),
        # WorkflowMemoryModel
        migrations.AddField(
            model_name="workflowmemorymodel",
            name="user_id",
            field=models.IntegerField(null=True, blank=True, db_index=True),
        ),
        # ConceptualMemoryModel
        migrations.AddField(
            model_name="conceptualmemorymodel",
            name="user_id",
            field=models.IntegerField(null=True, blank=True, db_index=True),
        ),
        # Backfill existing rows
        migrations.RunPython(backfill_process_user_ids, migrations.RunPython.noop),
        migrations.RunPython(backfill_task_user_ids, migrations.RunPython.noop),
        migrations.RunPython(backfill_run_user_ids, migrations.RunPython.noop),
        migrations.RunPython(backfill_memory_user_ids, migrations.RunPython.noop),
    ]
