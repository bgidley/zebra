"""Commons secret keys in a ``CredentialStore``.

The Zebra key lives under ``integration_name="commons-zebra"`` and the device key under
``"commons-device"`` (credential type ``secret_key``, hex). Commons belongs to the
deployment, not a user, so keys are namespaced by a fixed instance name: changing the
owner must not lose them. Secret values are never logged.
"""

from __future__ import annotations

import logging

from zebra_agent.commons import keys
from zebra_agent.storage.interfaces import CredentialStore

logger = logging.getLogger(__name__)

ZEBRA_KEY_INTEGRATION = "commons-zebra"
DEVICE_KEY_INTEGRATION = "commons-device"
SECRET_KEY_TYPE = "secret_key"
INSTANCE_NAMESPACE = "instance"


class CommonsKeys:
    """Read, create, back up and restore the Zebra and device secret keys."""

    def __init__(self, store: CredentialStore, namespace: str = INSTANCE_NAMESPACE) -> None:
        self._store = store
        self._namespace = namespace

    def __repr__(self) -> str:
        return f"CommonsKeys(namespace={self._namespace!r})"

    async def _get(self, integration: str) -> str | None:
        value = await self._store.get(self._namespace, integration, SECRET_KEY_TYPE)
        if not value:
            return None
        try:
            keys.public_key(value)
        except keys.InvalidKeyError:
            logger.error("Stored %s key is not a valid secret key; ignoring it", integration)
            return None
        return value

    async def device_secret(self) -> str | None:
        """The device secret key, or None if not created yet."""
        return await self._get(DEVICE_KEY_INTEGRATION)

    async def get_or_create_device_secret(self) -> str:
        """The device secret key, created on first use."""
        secret = await self.device_secret()
        if secret is None:
            secret = keys.generate_secret_key()
            await self._store.set(self._namespace, DEVICE_KEY_INTEGRATION, SECRET_KEY_TYPE, secret)
            logger.info("Created Commons device key %s", keys.public_key(secret)[:16])
        return secret

    async def zebra_secret(self) -> str | None:
        """The Zebra secret key, or None when this device does not hold it."""
        return await self._get(ZEBRA_KEY_INTEGRATION)

    async def create_zebra_secret(self) -> str:
        """Create the Zebra key. Refuses if one is already held (that would be a new identity)."""
        if await self.zebra_secret() is not None:
            raise ValueError("this device already holds a Zebra key")
        secret = keys.generate_secret_key()
        await self._store.set(self._namespace, ZEBRA_KEY_INTEGRATION, SECRET_KEY_TYPE, secret)
        logger.info("Created Zebra key %s", keys.public_key(secret)[:16])
        return secret

    async def export_backup(self) -> str:
        """The Zebra key as an ``nsec`` for offline backup. Raises if not held."""
        secret = await self.zebra_secret()
        if secret is None:
            raise ValueError("this device does not hold the Zebra key")
        return keys.nsec_encode(secret)

    async def restore_backup(self, nsec: str) -> str:
        """Store the Zebra key from an ``nsec`` backup; returns its public key.

        Raises ``keys.InvalidKeyError`` when the text is not a valid ``nsec``.
        """
        secret = keys.nsec_decode(nsec)
        await self._store.set(self._namespace, ZEBRA_KEY_INTEGRATION, SECRET_KEY_TYPE, secret)
        pubkey = keys.public_key(secret)
        logger.info("Restored Zebra key %s from backup", pubkey[:16])
        return pubkey
