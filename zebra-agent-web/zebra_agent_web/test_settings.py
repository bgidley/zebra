"""Test settings — inherits from production settings but uses SQLite.

Only imported during pytest runs for zebra-agent-web unit tests.
"""

from zebra_agent_web.settings import *  # noqa: F401, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "OPTIONS": {
            "timeout": 20,
        },
    }
}

# Remove SetupRedirectMiddleware in tests to avoid SQLite lock contention
# on User.objects.exists() across hundreds of concurrent test requests.
if "zebra_agent_web.middleware.SetupRedirectMiddleware" in MIDDLEWARE:  # noqa: F405
    MIDDLEWARE.remove("zebra_agent_web.middleware.SetupRedirectMiddleware")  # noqa: F405

# Disable secure cookies for tests
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
