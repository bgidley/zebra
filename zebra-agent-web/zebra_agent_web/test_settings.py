"""Test settings — inherits from production settings but uses SQLite.

Only imported during pytest runs for zebra-agent-web unit tests.
"""

from zebra_agent_web.settings import *  # noqa: F401, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
