"""Django app configuration for Zebra API."""

from django.apps import AppConfig


class ApiConfig(AppConfig):
    """Configuration for the Zebra API app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "zebra_web.api"
    verbose_name = "Zebra API"

    def ready(self):
        """Initialize the Zebra engine when Django starts."""
        # Import here to avoid circular imports
        from zebra_web.api import engine

        engine.initialize()
