"""E2E test settings — forces file-based SQLite regardless of environment.

Used by CI e2e job via --ds=zebra_agent_web.e2e_settings so that Django
never picks up Oracle DSN from the CI environment. File-based SQLite is
required (not :memory:) because e2e tests hit the API via Django's test
client, which opens new connections that must see the same DB as the test.
"""

from pathlib import Path

from zebra_agent_web.settings import *  # noqa: F401, F403

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            "timeout": 20,
        },
    }
}

# Use memory cache for sessions to avoid SQLite lock contention
SESSION_ENGINE = "django.contrib.sessions.backends.cache"

# Disable secure cookies for tests
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
