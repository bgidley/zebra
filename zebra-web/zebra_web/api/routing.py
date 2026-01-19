"""WebSocket URL routing for Zebra API."""

from django.urls import path

from zebra_web.api.consumers import WorkflowConsumer

websocket_urlpatterns = [
    path("ws/", WorkflowConsumer.as_asgi()),
]
