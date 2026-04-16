"""Django app configuration for Zebra Agent Web API."""

from django.apps import AppConfig


class ApiConfig(AppConfig):
    """Configuration for the API app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "zebra_agent_web.api"
    verbose_name = "Zebra Agent API"

    def ready(self):
        """Initialize the Zebra agent when Django starts."""
        from zebra_agent_web.api import agent_engine, engine

        # Mark engines for lazy initialization
        engine.initialize()
        agent_engine.initialize()
