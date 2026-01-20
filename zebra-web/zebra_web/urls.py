"""URL configuration for zebra-web project."""

from django.urls import include, path

from zebra_web.api import web_views, agent_views

urlpatterns = [
    # API endpoints (JSON)
    path("api/", include("zebra_web.api.urls")),
    # Web UI (HTML + HTMX)
    path("", web_views.dashboard, name="dashboard"),
    # Definitions
    path("definitions/", web_views.definitions_list, name="definitions_list"),
    path("definitions/create/", web_views.definition_create, name="definition_create"),
    path("definitions/<str:definition_id>/", web_views.definition_detail, name="definition_detail"),
    path(
        "definitions/<str:definition_id>/delete/",
        web_views.definition_delete,
        name="definition_delete",
    ),
    # Processes
    path("processes/", web_views.processes_list, name="processes_list"),
    path("processes/start/", web_views.process_start, name="process_start"),
    path("processes/<str:process_id>/", web_views.process_detail, name="process_detail"),
    path("processes/<str:process_id>/pause/", web_views.process_pause, name="process_pause"),
    path("processes/<str:process_id>/resume/", web_views.process_resume, name="process_resume"),
    path("processes/<str:process_id>/delete/", web_views.process_delete, name="process_delete"),
    # Tasks
    path("tasks/", web_views.tasks_list, name="tasks_list"),
    path("tasks/<str:task_id>/", web_views.task_detail, name="task_detail"),
    path("tasks/<str:task_id>/complete/", web_views.task_complete, name="task_complete"),
    # Agent
    path("agent/", agent_views.agent_dashboard, name="agent_dashboard"),
    path("agent/workflows/", agent_views.workflow_library, name="workflow_library"),
    path("agent/workflows/create/", agent_views.workflow_create, name="workflow_create"),
    path(
        "agent/workflows/<str:workflow_name>/", agent_views.workflow_detail, name="workflow_detail"
    ),
    path(
        "agent/workflows/<str:workflow_name>/delete/",
        agent_views.workflow_delete,
        name="workflow_delete",
    ),
    path("agent/run/", agent_views.run_goal_form, name="run_goal_form"),
    path("agent/run/execute/", agent_views.run_goal_execute, name="run_goal_execute"),
    path("agent/runs/", agent_views.recent_runs, name="recent_runs"),
    path("agent/runs/<str:run_id>/", agent_views.run_detail, name="run_detail"),
    path("agent/runs/<str:run_id>/rate/", agent_views.run_rate, name="run_rate"),
]
