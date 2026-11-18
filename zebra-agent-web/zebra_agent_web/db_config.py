"""Database selection for Zebra's Django settings (#305).

``ZEBRA_DB_ENGINE`` picks the backend: ``oracle``, ``postgresql`` (alias
``postgres``) or ``sqlite``. Unset, it stays backward compatible: Oracle when
``ORACLE_DSN`` is set, else SQLite. An unknown value fails loudly rather than
silently falling back to SQLite (a running Zebra must not land on SQLite).

PostgreSQL reads the standard libpq variables: ``PGHOST``, ``PGPORT``,
``PGDATABASE``, ``PGUSER``, ``PGPASSWORD`` (``PGSSLMODE`` and friends are read
by libpq itself).
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from django.core.exceptions import ImproperlyConfigured

ORACLE = "oracle"
POSTGRESQL = "postgresql"
SQLITE = "sqlite"

_ALIASES = {
    "oracle": ORACLE,
    "postgresql": POSTGRESQL,
    "postgres": POSTGRESQL,
    "sqlite": SQLITE,
    "sqlite3": SQLITE,
}


def db_engine(env: Mapping[str, str]) -> str:
    """Return the selected engine name (``oracle`` / ``postgresql`` / ``sqlite``).

    Raises:
        ImproperlyConfigured: If ``ZEBRA_DB_ENGINE`` names an unsupported engine.
    """
    raw = (env.get("ZEBRA_DB_ENGINE") or "").strip().lower()
    if not raw:
        return ORACLE if env.get("ORACLE_DSN") else SQLITE
    try:
        return _ALIASES[raw]
    except KeyError:
        raise ImproperlyConfigured(
            f"ZEBRA_DB_ENGINE={raw!r} is not supported; use oracle, postgresql or sqlite"
        ) from None


def database_config(env: Mapping[str, str], sqlite_path: Path | str) -> dict[str, Any]:
    """Build Django's ``DATABASES["default"]`` from the environment."""
    engine = db_engine(env)
    if engine == ORACLE:
        return {
            "ENGINE": "zebra_agent_web.db_backends.oracle",
            "NAME": env.get("ORACLE_DSN", ""),
            "USER": env.get("ORACLE_USERNAME", ""),
            "PASSWORD": env.get("ORACLE_PASSWORD", ""),
        }
    if engine == POSTGRESQL:
        return {
            "ENGINE": "zebra_agent_web.db_backends.postgresql",
            "NAME": env.get("PGDATABASE", "zebra"),
            "USER": env.get("PGUSER", "zebra"),
            "PASSWORD": env.get("PGPASSWORD", ""),
            "HOST": env.get("PGHOST", "localhost"),
            "PORT": env.get("PGPORT", "5432"),
        }
    return {"ENGINE": "django.db.backends.sqlite3", "NAME": sqlite_path}
