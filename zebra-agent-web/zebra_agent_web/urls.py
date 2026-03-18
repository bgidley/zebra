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
    # API endpoints (JSON)
    path("api/", include("zebra_agent_web.api.urls")),
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
        "workflows/<str:workflow_name>/delete/",
        web_views.workflow_delete,
        name="workflow_delete",
    ),
    # Human Tasks (form pages still accessible directly)
    path("tasks/<str:task_id>/", web_views.human_task_form, name="human_task_form"),
    path("tasks/<str:task_id>/submit/", web_views.human_task_submit, name="human_task_submit"),
    # Run detail pages
    path("runs/<str:run_id>/", web_views.run_detail, name="run_detail"),
    path("runs/<str:run_id>/rate/", web_views.run_rate, name="run_rate"),
    path("runs/<str:run_id>/feedback/", web_views.run_feedback, name="run_feedback"),
    # Legacy redirects (old URLs redirect to activity page)
    path("tasks/", web_views.pending_tasks, name="pending_tasks"),
    path("runs/in-progress/", web_views.in_progress_runs, name="in_progress_runs"),
    path("runs/", web_views.recent_runs, name="recent_runs"),
]
