"""URL patterns for Zebra API."""

from django.urls import path

from zebra_web.api import views

urlpatterns = [
    # Health check
    path("health/", views.health_check, name="health_check"),
    # Definitions
    path("definitions/", views.definitions_list, name="definitions_list"),
    path("definitions/<str:definition_id>/", views.definition_detail, name="definition_detail"),
    # Processes
    path("processes/", views.processes_list, name="processes_list"),
    path("processes/<str:process_id>/", views.process_detail, name="process_detail"),
    path("processes/<str:process_id>/pause/", views.process_pause, name="process_pause"),
    path("processes/<str:process_id>/resume/", views.process_resume, name="process_resume"),
    path("processes/<str:process_id>/tasks/", views.process_tasks, name="process_tasks"),
    # Tasks
    path("tasks/", views.pending_tasks, name="pending_tasks"),
    path("tasks/<str:task_id>/", views.task_detail, name="task_detail"),
    path("tasks/<str:task_id>/complete/", views.task_complete, name="task_complete"),
]
