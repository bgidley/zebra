"""Test settings — inherits from production settings but uses SQLite.

Only imported during pytest runs for zebra-agent-web unit tests.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from zebra_agent_web.db_config import POSTGRESQL, SQLITE, database_config, db_engine
from zebra_agent_web.settings import *  # noqa: F401, F403

# ZEBRA_TEST_DB_ENGINE=postgresql runs the unit suite against PostgreSQL (PG* env vars;
# Django creates and drops a test_<PGDATABASE> database), so ORM differences SQLite
# hides are caught (#305). Default: in-memory SQLite.
_test_engine = os.environ.get("ZEBRA_TEST_DB_ENGINE", "").strip().lower()
if _test_engine and db_engine({"ZEBRA_DB_ENGINE": _test_engine}) not in (POSTGRESQL, SQLITE):
    raise ImproperlyConfigured(
        f"ZEBRA_TEST_DB_ENGINE={_test_engine!r}: unit tests run on postgresql or sqlite"
    )
if _test_engine and db_engine({"ZEBRA_DB_ENGINE": _test_engine}) == POSTGRESQL:
    DATABASES = {"default": database_config({**os.environ, "ZEBRA_DB_ENGINE": POSTGRESQL}, "")}
else:
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
