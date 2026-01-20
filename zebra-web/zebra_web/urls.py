"""URL configuration for zebra-web project."""

from django.urls import include, path

from zebra_web.api import web_views

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
]
