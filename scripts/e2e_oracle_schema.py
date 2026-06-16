#!/usr/bin/env python3
"""Provision/drop ephemeral Oracle schemas for e2e CI runs.

Each pipeline run gets its own throwaway Oracle user (schema) so feature-branch
e2e tests run against real Oracle (prod parity) with full isolation — no shared
schema to collide on, and none of the async-Django + SQLite cross-connection
visibility flakiness.

Connects as a dedicated least-privilege provisioner read from the environment:
    E2E_PROVISIONER_DSN / E2E_PROVISIONER_USERNAME / E2E_PROVISIONER_PASSWORD

The provisioner needs (one-time, granted by ADB ADMIN). Note: on Autonomous DB
`GRANT ANY ROLE/PRIVILEGE` do NOT let it pass roles on, so the grantable roles
and privs must be held WITH ADMIN OPTION:
    GRANT CREATE SESSION, CREATE USER, ALTER USER, DROP USER TO E2E_PROVISIONER;
    GRANT CONNECT, RESOURCE, CREATE VIEW TO E2E_PROVISIONER WITH ADMIN OPTION;
    GRANT SELECT_CATALOG_ROLE TO E2E_PROVISIONER;   -- for `reap`

Usage:
    e2e_oracle_schema.py create --schema E2E_FOO_123 --out e2e_db.env
    e2e_oracle_schema.py drop   --schema E2E_FOO_123
    e2e_oracle_schema.py reap   --older-than 6h
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import sys
from datetime import UTC, datetime, timedelta

import oracledb

# Oracle unquoted identifier: starts with a letter, then letters/digits/underscore.
# We cap at 30 chars to stay valid on every Oracle version.
SCHEMA_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,29}$")


def _conn() -> oracledb.Connection:
    """Connect as the provisioner from env vars."""
    try:
        dsn = os.environ["E2E_PROVISIONER_DSN"]
        user = os.environ["E2E_PROVISIONER_USERNAME"]
        password = os.environ["E2E_PROVISIONER_PASSWORD"]
    except KeyError as exc:
        sys.exit(f"missing required env var: {exc}")
    return oracledb.connect(user=user, password=password, dsn=dsn)


def _validate(schema: str) -> str:
    schema = schema.upper()
    if not SCHEMA_RE.match(schema):
        sys.exit(f"invalid schema name {schema!r} (must match {SCHEMA_RE.pattern})")
    return schema


def _gen_password() -> str:
    """ADB-complexity-safe password: upper + lower + digit, alnum only (no shell-quoting)."""
    return "Az9" + secrets.token_hex(12)


def _drop_user(cur, schema: str) -> None:
    try:
        cur.execute(f"DROP USER {schema} CASCADE")
    except oracledb.DatabaseError as exc:
        (err,) = exc.args
        if err.code != 1918:  # ORA-01918: user does not exist
            raise


def cmd_create(args: argparse.Namespace) -> None:
    schema = _validate(args.schema)
    password = _gen_password()
    with _conn() as conn:
        cur = conn.cursor()
        _drop_user(cur, schema)  # idempotent: clean any prior run with the same name
        cur.execute(f"CREATE USER {schema} IDENTIFIED BY {password}")
        # Standard Django-on-Oracle privilege set. On Autonomous DB, grant quota
        # via ALTER USER (UNLIMITED TABLESPACE is restricted); the default user
        # tablespace on ADB is DATA.
        cur.execute(f"GRANT CONNECT, RESOURCE, CREATE VIEW TO {schema}")
        cur.execute(f"ALTER USER {schema} QUOTA UNLIMITED ON DATA")
        conn.commit()

    dsn = os.environ["E2E_PROVISIONER_DSN"]  # schema lives in the same ADB as the provisioner
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(f"ORACLE_DSN={dsn}\n")
            fh.write(f"ORACLE_USERNAME={schema}\n")
            fh.write(f"ORACLE_PASSWORD={password}\n")
    print(schema)


def cmd_drop(args: argparse.Namespace) -> None:
    schema = _validate(args.schema)
    with _conn() as conn:
        _drop_user(conn.cursor(), schema)
        conn.commit()
    print(f"dropped {schema}")


def _parse_age(spec: str) -> timedelta:
    m = re.fullmatch(r"(\d+)([hm])", spec)
    if not m:
        sys.exit("--older-than must look like '6h' or '30m'")
    n, unit = int(m.group(1)), m.group(2)
    return timedelta(hours=n) if unit == "h" else timedelta(minutes=n)


def cmd_reap(args: argparse.Namespace) -> None:
    """Drop orphaned E2E_* schemas left by killed jobs (needs SELECT_CATALOG_ROLE)."""
    cutoff = datetime.now(UTC) - _parse_age(args.older_than)
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            r"SELECT username, created FROM dba_users "
            r"WHERE username LIKE 'E2E\_%' ESCAPE '\'"
        )
        rows = cur.fetchall()
        dropped = []
        for username, created in rows:
            if created.replace(tzinfo=UTC) < cutoff:
                _drop_user(cur, username)
                dropped.append(username)
        conn.commit()
    print(f"reaped {len(dropped)} schema(s): {', '.join(dropped) or '(none)'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="create an ephemeral schema")
    p_create.add_argument("--schema", required=True)
    p_create.add_argument("--out", help="write ORACLE_* env file for the new schema")
    p_create.set_defaults(func=cmd_create)

    p_drop = sub.add_parser("drop", help="drop a schema")
    p_drop.add_argument("--schema", required=True)
    p_drop.set_defaults(func=cmd_drop)

    p_reap = sub.add_parser("reap", help="drop orphaned E2E_* schemas older than a cutoff")
    p_reap.add_argument("--older-than", default="6h")
    p_reap.set_defaults(func=cmd_reap)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
