"""WebSocket URL routing for Zebra Agent Web."""

from django.urls import path

# WebSocket URL patterns - can be extended for real-time features
websocket_urlpatterns = [
    # Add WebSocket consumers here if needed
    # path("ws/agent/", AgentConsumer.as_asgi()),
]
