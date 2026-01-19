"""URL configuration for zebra-web project."""

from django.urls import include, path

urlpatterns = [
    path("api/", include("zebra_web.api.urls")),
]
