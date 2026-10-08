"""URL configuration for zebra-agent-web project.

This is an agent-only web application with simplified URL structure:
- / -> Dashboard
- /run/ -> Run Goal
- /activity/ -> Activity (goals, tasks, history)
- /workflows/ -> Workflow Library
- /api/ -> REST API
"""

from django.urls import include, path

from zebra_agent_web.api import web_views

urlpatterns = [
    # Auth endpoints (passkey)
    path("auth/", include("zebra_agent_web.api.auth_urls")),
    # API endpoints (JSON)
    path("api/", include("zebra_agent_web.api.urls")),
    # First-run setup
    path("setup/", web_views.setup_view, name="setup"),
    # Web UI (HTML + HTMX) - Agent focused
    path("", web_views.dashboard, name="dashboard"),
    # Run Goal
    path("run/", web_views.run_goal_form, name="run_goal_form"),
    path("run/execute/", web_views.run_goal_execute, name="run_goal_execute"),
    path("run/queue/", web_views.run_goal_queue, name="run_goal_queue"),
    # Activity (unified view: in-progress, pending tasks, history)
    path("activity/", web_views.activity, name="activity"),
    # Workflows
    path("workflows/", web_views.workflow_library, name="workflow_library"),
    path("workflows/create/", web_views.workflow_create, name="workflow_create"),
    path("workflows/<str:workflow_name>/", web_views.workflow_detail, name="workflow_detail"),
    path(
        "workflows/<str:workflow_name>/retire/",
        web_views.workflow_retire,
        name="workflow_retire",
    ),
    path(
        "workflows/<str:workflow_name>/restore/",
        web_views.workflow_restore,
        name="workflow_restore",
    ),
    path(
        "workflows/<str:workflow_name>/delete/",
        web_views.workflow_delete,
        name="workflow_delete",
    ),
    # Process actions (HTMX)
    path(
        "processes/<str:process_id>/cancel/",
        web_views.cancel_process,
        name="cancel_process",
    ),
    path(
        "processes/bulk-cancel/",
        web_views.bulk_cancel_processes,
        name="bulk_cancel_processes",
    ),
    # Human Tasks (form pages still accessible directly)
    path("tasks/<str:task_id>/", web_views.human_task_form, name="human_task_form"),
    path("tasks/<str:task_id>/submit/", web_views.human_task_submit, name="human_task_submit"),
    # Tasks flagged for manual review by recovery (#130)
    path("tasks/<str:task_id>/retry/", web_views.review_task_retry, name="review_task_retry"),
    path("tasks/<str:task_id>/fail/", web_views.review_task_fail, name="review_task_fail"),
    # Values Profile (F18) — starts the wizard for capture or edit
    path("profile/values/", web_views.values_profile_wizard, name="values_profile_wizard"),
    # Values taxonomy curation (#106)
    path("profile/taxonomy/", web_views.values_taxonomy_page, name="values_taxonomy"),
    path(
        "profile/taxonomy/action/",
        web_views.values_taxonomy_action,
        name="values_taxonomy_action",
    ),
    # Trust management (F15, F16, F17)
    path("trust/", web_views.trust_page, name="trust_page"),
    path("trust/pause-all/", web_views.trust_pause_all_form, name="trust_pause_all_form"),
    path(
        "trust/freeing/<str:action>/",
        web_views.trust_freeing_action_form,
        name="trust_freeing_action_form",
    ),
    path("trust/<str:domain>/set/", web_views.trust_set_level_form, name="trust_set_level_form"),
    path(
        "trust/suggestions/<str:suggestion_id>/resolve/",
        web_views.trust_suggestion_resolve_form,
        name="trust_suggestion_resolve_form",
    ),
    # Personal Knowledge Store (F31)
    path("knowledge/", web_views.knowledge_list, name="knowledge_list"),
    path("knowledge/create/", web_views.knowledge_create, name="knowledge_create"),
    path("knowledge/<str:entry_id>/edit/", web_views.knowledge_edit, name="knowledge_edit"),
    path("knowledge/<str:entry_id>/delete/", web_views.knowledge_delete, name="knowledge_delete"),
    # Run detail pages
    path("runs/<str:run_id>/", web_views.run_detail, name="run_detail"),
    path("runs/<str:run_id>/context/", web_views.run_context_partial, name="run_context_partial"),
    path("runs/<str:run_id>/rate/", web_views.run_rate, name="run_rate"),
    path("runs/<str:run_id>/feedback/", web_views.run_feedback, name="run_feedback"),
    path("runs/<str:run_id>/continue/", web_views.run_continue, name="run_continue"),
    # Ethics Audit Log (F20 / REQ-ETH-006)
    path("ethics-audit/", web_views.ethics_audit, name="ethics_audit"),
    # Legacy redirects (old URLs redirect to activity page)
    path("tasks/", web_views.pending_tasks, name="pending_tasks"),
    path("runs/in-progress/", web_views.in_progress_runs, name="in_progress_runs"),
    path("runs/", web_views.recent_runs, name="recent_runs"),
]
