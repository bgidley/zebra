"""Command-line interface for Zebra Agent.

Provides the ``zebra-agent`` console command with subcommand groups for
managing credentials, goals, and other agent configuration.

Usage::

    zebra-agent credential set github api_key <value>
    zebra-agent credential get github api_key
    zebra-agent credential list
    zebra-agent credential delete github api_key
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

logger = logging.getLogger(__name__)

# Default user ID when none is supplied — single-tenant CLI usage.
_DEFAULT_USER_ID = "default"


# ---------------------------------------------------------------------------
# Credential commands
# ---------------------------------------------------------------------------


async def _credential_set(
    user_id: str, integration: str, cred_type: str, value: str, backend: str
) -> None:
    store = _make_store(backend)
    await store.set(user_id, integration, cred_type, value)
    print(f"Credential stored: {integration}/{cred_type} for user '{user_id}'")


async def _credential_get(user_id: str, integration: str, cred_type: str, backend: str) -> None:
    store = _make_store(backend)
    value = await store.get(user_id, integration, cred_type)
    if value is None:
        print(f"No credential found for {integration}/{cred_type} (user '{user_id}')")
        sys.exit(1)
    # Mask all but the last 4 characters to avoid accidental exposure in
    # terminal recordings — the command exists for testing/verification only.
    masked = ("*" * max(0, len(value) - 4)) + value[-4:]
    print(f"{integration}/{cred_type}: {masked}")


async def _credential_list(user_id: str, backend: str) -> None:
    store = _make_store(backend)
    keys = await store.list(user_id)
    if not keys:
        print(f"No credentials stored for user '{user_id}'")
        return
    print(f"Credentials for user '{user_id}':")
    for key in keys:
        print(f"  {key.integration_name}/{key.credential_type}")


async def _credential_delete(user_id: str, integration: str, cred_type: str, backend: str) -> None:
    store = _make_store(backend)
    await store.delete(user_id, integration, cred_type)
    print(f"Credential deleted: {integration}/{cred_type} for user '{user_id}'")


def _make_store(backend: str):
    """Instantiate the appropriate CredentialStore backend."""
    if backend == "keyring":
        from zebra_agent.storage.credentials import KeyringCredentialStore

        return KeyringCredentialStore()
    elif backend == "file":
        from zebra_agent.storage.credentials import FileCredentialStore

        return FileCredentialStore()
    else:
        from zebra_agent.storage.interfaces import InMemoryCredentialStore

        return InMemoryCredentialStore()


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zebra-agent",
        description="Zebra Agent CLI",
    )
    parser.add_argument(
        "--user",
        default=_DEFAULT_USER_ID,
        metavar="USER_ID",
        help="User identifier (default: 'default')",
    )
    parser.add_argument(
        "--backend",
        choices=["keyring", "file", "memory"],
        default="keyring",
        help="Credential backend (default: keyring)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    subparsers = parser.add_subparsers(dest="group", metavar="GROUP")

    # ---- credential group ----
    cred_parser = subparsers.add_parser(
        "credential",
        help="Manage integration credentials",
    )
    cred_sub = cred_parser.add_subparsers(dest="command", metavar="COMMAND")

    # credential set
    set_p = cred_sub.add_parser("set", help="Store a credential")
    set_p.add_argument("integration", help="Integration name (e.g. github)")
    set_p.add_argument("cred_type", metavar="type", help="Credential type (e.g. api_key)")
    set_p.add_argument("value", help="Credential value")

    # credential get
    get_p = cred_sub.add_parser("get", help="Retrieve a credential (masked output)")
    get_p.add_argument("integration", help="Integration name")
    get_p.add_argument("cred_type", metavar="type", help="Credential type")

    # credential list
    cred_sub.add_parser("list", help="List all stored credential keys for the user")

    # credential delete
    del_p = cred_sub.add_parser("delete", help="Delete a credential")
    del_p.add_argument("integration", help="Integration name")
    del_p.add_argument("cred_type", metavar="type", help="Credential type")

    return parser


def main() -> None:
    """Entry point for the ``zebra-agent`` CLI command."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    if args.group is None:
        parser.print_help()
        sys.exit(0)

    if args.group == "credential":
        _run_credential_command(args)
    else:
        parser.print_help()
        sys.exit(1)


def _run_credential_command(args: argparse.Namespace) -> None:
    """Dispatch to the appropriate credential sub-command."""
    if args.command is None:
        # No sub-command given
        print("Usage: zebra-agent credential {set,get,list,delete} ...")
        sys.exit(1)

    user_id = args.user
    backend = args.backend

    if args.command == "set":
        asyncio.run(_credential_set(user_id, args.integration, args.cred_type, args.value, backend))
    elif args.command == "get":
        asyncio.run(_credential_get(user_id, args.integration, args.cred_type, backend))
    elif args.command == "list":
        asyncio.run(_credential_list(user_id, backend))
    elif args.command == "delete":
        asyncio.run(_credential_delete(user_id, args.integration, args.cred_type, backend))
    else:
        print(f"Unknown credential command: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
