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

# Use memory cache for sessions to avoid SQLite lock contention
SESSION_ENGINE = "django.contrib.sessions.backends.cache"

# Remove SetupRedirectMiddleware in tests to avoid SQLite lock contention
# on User.objects.exists() across hundreds of concurrent test requests.
if "zebra_agent_web.middleware.SetupRedirectMiddleware" in MIDDLEWARE:  # noqa: F405
    MIDDLEWARE.remove("zebra_agent_web.middleware.SetupRedirectMiddleware")  # noqa: F405

# Remove LoginRequiredMiddleware in tests so anonymous clients can access all views.
# Individual views that require auth are still protected by @login_required.
if "django.contrib.auth.middleware.LoginRequiredMiddleware" in MIDDLEWARE:  # noqa: F405
    MIDDLEWARE.remove("django.contrib.auth.middleware.LoginRequiredMiddleware")  # noqa: F405

# Disable secure cookies for tests
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
