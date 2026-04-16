"""WebSocket URL routing for Zebra Agent Web."""

from django.urls import path

from zebra_agent_web.api.consumers import GoalProgressConsumer

# WebSocket URL patterns for real-time goal progress updates
websocket_urlpatterns = [
    path("ws/goal/<str:run_id>/", GoalProgressConsumer.as_asgi()),
]
