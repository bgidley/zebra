"""REST API URL patterns for Zebra Agent.

Provides JSON API endpoints for:
- Agent operations (workflows, goals, runs)
- Execution monitoring (processes, tasks)
"""

from django.urls import path

from zebra_agent_web.api import views

urlpatterns = [
    # Health check
    path("health/", views.health_check, name="api_health_check"),
    # Workflow endpoints
    path("workflows/", views.workflows_list, name="api_workflows_list"),
    path("workflows/<str:workflow_name>/", views.workflow_detail, name="api_workflow_detail"),
    path("workflows/<str:workflow_name>/stats/", views.workflow_stats, name="api_workflow_stats"),
    # Goal execution
    path("goals/", views.execute_goal, name="api_execute_goal"),
    # Run endpoints
    path("runs/", views.runs_list, name="api_runs_list"),
    path("runs/<str:run_id>/", views.run_detail, name="api_run_detail"),
    path("runs/<str:run_id>/rate/", views.run_rate, name="api_run_rate"),
    path("runs/<str:run_id>/status/", views.run_status, name="api_run_status"),
    path("runs/<str:run_id>/diagram/", views.run_diagram, name="api_run_diagram"),
    # Execution monitoring (processes and tasks)
    path("processes/", views.processes_list, name="api_processes_list"),
    path("processes/<str:process_id>/", views.process_detail, name="api_process_detail"),
    path("processes/<str:process_id>/tasks/", views.process_tasks, name="api_process_tasks"),
    path("tasks/<str:task_id>/", views.task_detail, name="api_task_detail"),
    path("tasks/<str:task_id>/complete/", views.task_complete, name="api_task_complete"),
]
