"""Tests for the credential store implementations.

Covers:
- InMemoryCredentialStore: full CRUD and list
- FileCredentialStore: CRUD, list, permissions, path sanitisation
- KeyringCredentialStore: behaviour when keyring is absent
- ScrubCredentialsFilter: log message redaction
- CLI: argument parsing and dispatch
- ZebraContainer: credential_store is registered by default
"""

from __future__ import annotations

import logging
import stat
from pathlib import Path

import pytest

from zebra_agent.logging_filters import ScrubCredentialsFilter
from zebra_agent.storage.credentials import FileCredentialStore, KeyringCredentialStore
from zebra_agent.storage.interfaces import CredentialKey, InMemoryCredentialStore

# ---------------------------------------------------------------------------
# InMemoryCredentialStore
# ---------------------------------------------------------------------------


class TestInMemoryCredentialStore:
    async def test_set_and_get(self):
        store = InMemoryCredentialStore()
        await store.set("alice", "github", "api_key", "ghp_secret")
        value = await store.get("alice", "github", "api_key")
        assert value == "ghp_secret"

    async def test_get_missing_returns_none(self):
        store = InMemoryCredentialStore()
        value = await store.get("alice", "github", "api_key")
        assert value is None

    async def test_delete_removes_credential(self):
        store = InMemoryCredentialStore()
        await store.set("alice", "github", "api_key", "ghp_secret")
        await store.delete("alice", "github", "api_key")
        value = await store.get("alice", "github", "api_key")
        assert value is None

    async def test_delete_nonexistent_is_noop(self):
        store = InMemoryCredentialStore()
        # Should not raise
        await store.delete("alice", "github", "api_key")

    async def test_list_returns_keys_for_user(self):
        store = InMemoryCredentialStore()
        await store.set("alice", "github", "api_key", "v1")
        await store.set("alice", "google", "oauth_token", "v2")
        await store.set("bob", "github", "api_key", "v3")

        keys = await store.list("alice")
        assert len(keys) == 2
        integrations = {k.integration_name for k in keys}
        assert "github" in integrations
        assert "google" in integrations
        # Bob's credentials should not appear
        assert all(k.user_id == "alice" for k in keys)

    async def test_list_empty_for_unknown_user(self):
        store = InMemoryCredentialStore()
        keys = await store.list("nobody")
        assert keys == []

    async def test_list_returns_credential_key_dataclasses(self):
        store = InMemoryCredentialStore()
        await store.set("alice", "stripe", "secret_key", "sk_test_abc")
        keys = await store.list("alice")
        assert len(keys) == 1
        key = keys[0]
        assert isinstance(key, CredentialKey)
        assert key.user_id == "alice"
        assert key.integration_name == "stripe"
        assert key.credential_type == "secret_key"

    async def test_overwrite_credential(self):
        store = InMemoryCredentialStore()
        await store.set("alice", "github", "api_key", "old")
        await store.set("alice", "github", "api_key", "new")
        value = await store.get("alice", "github", "api_key")
        assert value == "new"

    def test_repr_does_not_include_values(self):
        store = InMemoryCredentialStore()
        store._store[("alice", "github", "api_key")] = "super_secret"
        representation = repr(store)
        assert "super_secret" not in representation
        assert "InMemoryCredentialStore" in representation


# ---------------------------------------------------------------------------
# FileCredentialStore
# ---------------------------------------------------------------------------


@pytest.fixture
def file_store(tmp_path: Path) -> FileCredentialStore:
    return FileCredentialStore(base_dir=tmp_path / "creds")


class TestFileCredentialStore:
    async def test_set_and_get(self, file_store: FileCredentialStore):
        await file_store.set("alice", "github", "api_key", "ghp_secret")
        value = await file_store.get("alice", "github", "api_key")
        assert value == "ghp_secret"

    async def test_get_missing_returns_none(self, file_store: FileCredentialStore):
        value = await file_store.get("alice", "github", "api_key")
        assert value is None

    async def test_delete_removes_file(self, file_store: FileCredentialStore):
        await file_store.set("alice", "github", "api_key", "ghp_secret")
        await file_store.delete("alice", "github", "api_key")
        value = await file_store.get("alice", "github", "api_key")
        assert value is None

    async def test_delete_nonexistent_is_noop(self, file_store: FileCredentialStore):
        # Should not raise
        await file_store.delete("alice", "github", "api_key")

    async def test_file_permissions_are_0600(self, file_store: FileCredentialStore):
        await file_store.set("alice", "github", "api_key", "ghp_secret")
        cred_path = file_store._cred_path("alice", "github", "api_key")
        mode = stat.S_IMODE(cred_path.stat().st_mode)
        assert mode == (stat.S_IRUSR | stat.S_IWUSR), f"Expected 0600, got {oct(mode)}"

    async def test_list_returns_stored_keys(self, file_store: FileCredentialStore):
        await file_store.set("alice", "github", "api_key", "v1")
        await file_store.set("alice", "google", "oauth_token", "v2")
        keys = await file_store.list("alice")
        assert len(keys) == 2
        integrations = {k.integration_name for k in keys}
        assert {"github", "google"} == integrations

    async def test_list_updated_after_delete(self, file_store: FileCredentialStore):
        await file_store.set("alice", "github", "api_key", "v1")
        await file_store.set("alice", "google", "oauth_token", "v2")
        await file_store.delete("alice", "github", "api_key")
        keys = await file_store.list("alice")
        assert len(keys) == 1
        assert keys[0].integration_name == "google"

    async def test_list_empty_for_unknown_user(self, file_store: FileCredentialStore):
        keys = await file_store.list("nobody")
        assert keys == []

    async def test_path_sanitises_slashes(self, file_store: FileCredentialStore):
        """Directory traversal characters are replaced in path components."""
        await file_store.set("../evil", "integration", "type", "value")
        # Should not raise and should not escape the base_dir
        value = await file_store.get("../evil", "integration", "type")
        assert value == "value"

    async def test_overwrite_credential(self, file_store: FileCredentialStore):
        await file_store.set("alice", "github", "api_key", "old")
        await file_store.set("alice", "github", "api_key", "new")
        value = await file_store.get("alice", "github", "api_key")
        assert value == "new"
        # Index should still have exactly one entry
        keys = await file_store.list("alice")
        assert len(keys) == 1


# ---------------------------------------------------------------------------
# KeyringCredentialStore (without a real keychain)
# ---------------------------------------------------------------------------


class TestKeyringCredentialStoreFallback:
    """Tests for KeyringCredentialStore behaviour when keyring is unavailable.

    We patch ``builtins.__import__`` to simulate keyring being absent rather
    than relying on it not being installed.
    """

    def _make_unavailable_store(self) -> KeyringCredentialStore:
        store = KeyringCredentialStore()
        store._available = False
        return store

    async def test_get_returns_none_when_unavailable(self):
        store = self._make_unavailable_store()
        result = await store.get("alice", "github", "api_key")
        assert result is None

    async def test_set_raises_when_unavailable(self):
        store = self._make_unavailable_store()
        with pytest.raises(RuntimeError, match="keyring package not available"):
            await store.set("alice", "github", "api_key", "secret")

    async def test_delete_is_noop_when_unavailable(self):
        store = self._make_unavailable_store()
        # Should not raise
        await store.delete("alice", "github", "api_key")

    async def test_list_returns_empty_when_unavailable(self):
        store = self._make_unavailable_store()
        keys = await store.list("alice")
        assert keys == []

    async def test_list_returns_empty_even_when_available(self):
        """Keyring doesn't support enumeration — list() always returns []."""
        store = KeyringCredentialStore()
        keys = await store.list("alice")
        assert keys == []


# ---------------------------------------------------------------------------
# ScrubCredentialsFilter
# ---------------------------------------------------------------------------


class TestScrubCredentialsFilter:
    def _make_record(self, msg: str, args: tuple = ()) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=args,
            exc_info=None,
        )
        return record

    def test_redacts_api_key_in_message(self):
        f = ScrubCredentialsFilter()
        record = self._make_record("api_key=ghp_supersecret123")
        f.filter(record)
        assert "ghp_supersecret123" not in record.msg
        assert "<redacted>" in record.msg

    def test_redacts_token_in_message(self):
        f = ScrubCredentialsFilter()
        record = self._make_record("token=eyJhbGciOiJSUzI1NiJ9.secret")
        f.filter(record)
        assert "eyJhbGciOiJSUzI1NiJ9.secret" not in record.msg
        assert "<redacted>" in record.msg

    def test_redacts_password_in_message(self):
        f = ScrubCredentialsFilter()
        record = self._make_record("password=hunter2")
        f.filter(record)
        assert "hunter2" not in record.msg

    def test_leaves_non_credential_messages_intact(self):
        f = ScrubCredentialsFilter()
        record = self._make_record("Process started successfully with id=abc123")
        original = record.msg
        f.filter(record)
        assert record.msg == original

    def test_redacts_in_string_args(self):
        f = ScrubCredentialsFilter()
        record = self._make_record("value: %s", ("api_key=ghp_secret",))
        f.filter(record)
        assert isinstance(record.args, tuple)
        assert "ghp_secret" not in record.args[0]
        assert "<redacted>" in record.args[0]

    def test_non_string_args_are_left_untouched(self):
        f = ScrubCredentialsFilter()
        record = self._make_record("count: %d", (42,))
        f.filter(record)
        assert record.args == (42,)

    def test_filter_always_returns_true(self):
        """Filter must not block log records."""
        f = ScrubCredentialsFilter()
        record = self._make_record("anything")
        result = f.filter(record)
        assert result is True


# ---------------------------------------------------------------------------
# ZebraContainer integration
# ---------------------------------------------------------------------------


class TestZebraContainerCredentialStore:
    def test_credential_store_is_registered_by_default(self):
        from zebra_agent.ioc.container import ZebraContainer

        container = ZebraContainer()
        assert container.has_service("credential_store")

    def test_credential_store_instance_is_a_credential_store(self):
        from zebra_agent.ioc.container import ZebraContainer
        from zebra_agent.storage.interfaces import CredentialStore

        container = ZebraContainer()
        store = container.get_service("credential_store")
        assert isinstance(store, CredentialStore)

    def test_credential_store_can_be_overridden(self):
        from zebra_agent.ioc.container import ZebraContainer

        container = ZebraContainer()
        container.register_service("credential_store", InMemoryCredentialStore, singleton=True)
        store = container.get_service("credential_store")
        assert isinstance(store, InMemoryCredentialStore)


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


class TestCLIArgumentParsing:
    """Tests for CLI argument parsing (no actual credential I/O)."""

    def _parse(self, argv: list[str]) -> object:
        from zebra_agent.cli import _build_parser

        return _build_parser().parse_args(argv)

    def test_credential_set_parses(self):
        args = self._parse(["credential", "set", "github", "api_key", "mysecret"])
        assert args.group == "credential"
        assert args.command == "set"
        assert args.integration == "github"
        assert args.cred_type == "api_key"
        assert args.value == "mysecret"

    def test_credential_get_parses(self):
        args = self._parse(["credential", "get", "github", "api_key"])
        assert args.group == "credential"
        assert args.command == "get"
        assert args.integration == "github"
        assert args.cred_type == "api_key"

    def test_credential_list_parses(self):
        args = self._parse(["credential", "list"])
        assert args.group == "credential"
        assert args.command == "list"

    def test_credential_delete_parses(self):
        args = self._parse(["credential", "delete", "github", "api_key"])
        assert args.group == "credential"
        assert args.command == "delete"
        assert args.integration == "github"
        assert args.cred_type == "api_key"

    def test_default_user_is_default(self):
        args = self._parse(["credential", "list"])
        assert args.user == "default"

    def test_custom_user(self):
        args = self._parse(["--user", "alice", "credential", "list"])
        assert args.user == "alice"

    def test_backend_defaults_to_keyring(self):
        args = self._parse(["credential", "list"])
        assert args.backend == "keyring"

    def test_backend_can_be_file(self):
        args = self._parse(["--backend", "file", "credential", "list"])
        assert args.backend == "file"


# ---------------------------------------------------------------------------
# CLI end-to-end: set → get → list → delete using in-memory store
# ---------------------------------------------------------------------------


class TestCLIDispatch:
    """Integration tests that exercise the CLI dispatch with the memory backend."""

    async def test_set_and_get_via_cli_functions(self):
        # Use a real InMemoryCredentialStore but patch the make_store helper
        from unittest.mock import patch

        from zebra_agent.cli import _credential_get, _credential_set

        store = InMemoryCredentialStore()
        with patch("zebra_agent.cli._make_store", return_value=store):
            await _credential_set("alice", "github", "api_key", "ghp_test", "memory")
            # get should not raise for a known value
            await _credential_get("alice", "github", "api_key", "memory")

    async def test_list_via_cli_functions(self, capsys):
        from unittest.mock import patch

        from zebra_agent.cli import _credential_list

        store = InMemoryCredentialStore()
        await store.set("alice", "github", "api_key", "v1")
        with patch("zebra_agent.cli._make_store", return_value=store):
            await _credential_list("alice", "memory")
        captured = capsys.readouterr()
        assert "github" in captured.out
        assert "api_key" in captured.out

    async def test_delete_via_cli_functions(self, capsys):
        from unittest.mock import patch

        from zebra_agent.cli import _credential_delete

        store = InMemoryCredentialStore()
        await store.set("alice", "github", "api_key", "v1")
        with patch("zebra_agent.cli._make_store", return_value=store):
            await _credential_delete("alice", "github", "api_key", "memory")
        captured = capsys.readouterr()
        assert "deleted" in captured.out

    async def test_get_missing_credential_exits_with_error(self):
        from unittest.mock import patch

        from zebra_agent.cli import _credential_get

        store = InMemoryCredentialStore()
        with patch("zebra_agent.cli._make_store", return_value=store):
            with pytest.raises(SystemExit) as exc_info:
                await _credential_get("alice", "github", "api_key", "memory")
        assert exc_info.value.code == 1

    def test_make_store_file_backend(self):
        from zebra_agent.cli import _make_store

        store = _make_store("file")
        assert isinstance(store, FileCredentialStore)

    def test_make_store_keyring_backend(self):
        from zebra_agent.cli import _make_store

        store = _make_store("keyring")
        assert isinstance(store, KeyringCredentialStore)

    def test_make_store_memory_backend(self):
        from zebra_agent.cli import _make_store

        store = _make_store("memory")
        assert isinstance(store, InMemoryCredentialStore)
