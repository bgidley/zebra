"""Credential store implementations for Zebra Agent.

Provides secure credential storage backed by the OS keychain (macOS Keychain,
Secret Service on Linux, Windows Credential Manager) with a file-based fallback
for environments without a keychain.

Credentials are stored under the namespace ``zebra/<user_id>/<integration>/<type>``
and are NEVER logged or placed in process properties.
"""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path

from zebra_agent.storage.interfaces import CredentialKey, CredentialStore

logger = logging.getLogger(__name__)

# Namespace prefix used for all keyring entries.
_KEYRING_SERVICE_PREFIX = "zebra"


def _service_name(user_id: str, integration_name: str, credential_type: str) -> str:
    """Build the keyring service name for a credential."""
    return f"{_KEYRING_SERVICE_PREFIX}/{user_id}/{integration_name}/{credential_type}"


class KeyringCredentialStore(CredentialStore):
    """Credential store backed by the OS keychain via the ``keyring`` library.

    Uses the platform's native secure storage:
    - macOS: Keychain
    - Linux: Secret Service (via libsecret)
    - Windows: Windows Credential Manager
    - Fallback: keyring's own encrypted file backend

    Credentials are namespaced as ``zebra/<user_id>/<integration>/<type>`` so
    multiple users on the same machine are properly isolated.

    Note: The keyring library does not support enumeration on all backends,
    so ``list()`` always returns an empty list.  Use ``FileCredentialStore``
    if credential enumeration is required.
    """

    def __init__(self) -> None:
        try:
            import keyring  # noqa: F401

            self._available = True
        except ImportError:
            self._available = False
            logger.warning(
                "keyring package not available — KeyringCredentialStore will not function. "
                "Install with: pip install keyring"
            )

    async def get(
        self,
        user_id: str,
        integration_name: str,
        credential_type: str,
    ) -> str | None:
        """Retrieve a credential from the OS keychain.

        Args:
            user_id: User identifier (namespaces the credential).
            integration_name: Integration name (e.g. ``github``, ``google``).
            credential_type: Credential type (e.g. ``api_key``, ``token``).

        Returns:
            The stored credential value, or None if not found.
        """
        if not self._available:
            return None
        import keyring

        service = _service_name(user_id, integration_name, credential_type)
        value = keyring.get_password(service, integration_name)
        if value is not None:
            logger.debug(
                "Credential retrieved from keychain: user=%s integration=%s type=%s",
                user_id,
                integration_name,
                credential_type,
            )
        return value

    async def set(
        self,
        user_id: str,
        integration_name: str,
        credential_type: str,
        value: str,
    ) -> None:
        """Store a credential in the OS keychain.

        Args:
            user_id: User identifier.
            integration_name: Integration name.
            credential_type: Credential type.
            value: Credential value (never logged).
        """
        if not self._available:
            raise RuntimeError("keyring package not available. Install with: pip install keyring")
        import keyring

        service = _service_name(user_id, integration_name, credential_type)
        keyring.set_password(service, integration_name, value)
        logger.info(
            "Credential stored in keychain: user=%s integration=%s type=%s",
            user_id,
            integration_name,
            credential_type,
        )

    async def delete(
        self,
        user_id: str,
        integration_name: str,
        credential_type: str,
    ) -> None:
        """Remove a credential from the OS keychain.

        Args:
            user_id: User identifier.
            integration_name: Integration name.
            credential_type: Credential type.
        """
        if not self._available:
            return
        import keyring
        from keyring.errors import PasswordDeleteError

        service = _service_name(user_id, integration_name, credential_type)
        try:
            keyring.delete_password(service, integration_name)
            logger.info(
                "Credential deleted from keychain: user=%s integration=%s type=%s",
                user_id,
                integration_name,
                credential_type,
            )
        except PasswordDeleteError:
            # Already gone — treat as success
            logger.debug(
                "Credential not found in keychain (delete no-op): user=%s integration=%s type=%s",
                user_id,
                integration_name,
                credential_type,
            )

    async def list(self, user_id: str) -> list[CredentialKey]:
        """List credential keys for a user.

        Note: The keyring library does not support enumeration on all backends.
        This implementation always returns an empty list.  Use
        ``FileCredentialStore`` if enumeration is required.
        """
        logger.debug(
            "KeyringCredentialStore.list() called for user=%s — "
            "keyring does not support enumeration; returning empty list",
            user_id,
        )
        return []


def _safe_component(value: str) -> str:
    """Sanitise a path component to prevent directory traversal."""
    return value.replace("/", "_").replace("..", "_").replace("\x00", "_")


class FileCredentialStore(CredentialStore):
    """Credential store backed by the local filesystem.

    Stores credentials in ``~/.zebra-agent/credentials/`` (or a custom
    ``base_dir``) with strict 0600 permissions (owner read/write only).
    An index file per user tracks which keys exist to support enumeration
    via ``list()``.

    This backend is suitable for:
    - CI/CD environments without a keychain daemon
    - Containers and headless Linux servers
    - Development and testing

    Security model: files are protected by OS permissions.  Credential values
    are stored as plaintext within owner-only files; envelope encryption
    (REQ-DATA-006) is deferred to a future change.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or Path.home() / ".zebra-agent" / "credentials"

    def _ensure_dir(self) -> None:
        """Create the credentials directory with restricted permissions."""
        self._base_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self._base_dir, stat.S_IRWXU)

    def _cred_path(self, user_id: str, integration_name: str, credential_type: str) -> Path:
        """Return the file path for a credential."""
        return (
            self._base_dir
            / _safe_component(user_id)
            / _safe_component(integration_name)
            / f"{_safe_component(credential_type)}.cred"
        )

    def _index_path(self, user_id: str) -> Path:
        """Return the index file path for a user."""
        return self._base_dir / _safe_component(user_id) / ".index.json"

    def _read_index(self, user_id: str) -> list[dict]:
        path = self._index_path(user_id)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def _write_index(self, user_id: str, entries: list[dict]) -> None:
        path = self._index_path(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, stat.S_IRWXU)
        path.write_text(json.dumps(entries, indent=2))
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)

    async def get(
        self,
        user_id: str,
        integration_name: str,
        credential_type: str,
    ) -> str | None:
        """Retrieve a credential from the filesystem.

        Args:
            user_id: User identifier.
            integration_name: Integration name.
            credential_type: Credential type.

        Returns:
            The stored credential value, or None if not found.
        """
        path = self._cred_path(user_id, integration_name, credential_type)
        if not path.exists():
            return None
        try:
            value = path.read_text().strip()
            logger.debug(
                "Credential retrieved from file store: user=%s integration=%s type=%s",
                user_id,
                integration_name,
                credential_type,
            )
            return value or None
        except OSError as exc:
            logger.warning("Failed to read credential file %s: %s", path, exc)
            return None

    async def set(
        self,
        user_id: str,
        integration_name: str,
        credential_type: str,
        value: str,
    ) -> None:
        """Store a credential to the filesystem with 0600 permissions.

        Args:
            user_id: User identifier.
            integration_name: Integration name.
            credential_type: Credential type.
            value: Credential value (never logged).
        """
        self._ensure_dir()
        path = self._cred_path(user_id, integration_name, credential_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, stat.S_IRWXU)
        path.write_text(value)
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        logger.info(
            "Credential stored in file store: user=%s integration=%s type=%s",
            user_id,
            integration_name,
            credential_type,
        )
        # Update index
        entries = self._read_index(user_id)
        key = {
            "user_id": user_id,
            "integration_name": integration_name,
            "credential_type": credential_type,
        }
        if key not in entries:
            entries.append(key)
            self._write_index(user_id, entries)

    async def delete(
        self,
        user_id: str,
        integration_name: str,
        credential_type: str,
    ) -> None:
        """Remove a credential file from the filesystem.

        Args:
            user_id: User identifier.
            integration_name: Integration name.
            credential_type: Credential type.
        """
        path = self._cred_path(user_id, integration_name, credential_type)
        if path.exists():
            path.unlink()
            logger.info(
                "Credential deleted from file store: user=%s integration=%s type=%s",
                user_id,
                integration_name,
                credential_type,
            )
        # Update index
        entries = self._read_index(user_id)
        key = {
            "user_id": user_id,
            "integration_name": integration_name,
            "credential_type": credential_type,
        }
        if key in entries:
            entries.remove(key)
            self._write_index(user_id, entries)

    async def list(self, user_id: str) -> list[CredentialKey]:
        """List all credential keys stored for a user.

        Args:
            user_id: User identifier.

        Returns:
            List of CredentialKey dataclasses for this user.
        """
        entries = self._read_index(user_id)
        return [
            CredentialKey(
                user_id=e["user_id"],
                integration_name=e["integration_name"],
                credential_type=e["credential_type"],
            )
            for e in entries
        ]
