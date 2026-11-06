"""The ``nostr-sdk`` boundary: one relay connection and NIP-44 (#246, S3b-2).

The only module that imports ``nostr-sdk`` (Python bindings for rust-nostr, **alpha**), so it
can be swapped for a raw WebSocket in one place. Events stay our own ``Event`` (signed with
btclib in ``events.py``); nostr-sdk only carries their JSON.

Two quirks of nostr-sdk 0.45 shape this module:

- Its NIP-42 authenticator calls back into Python from a Rust thread and needs
  ``uniffi_set_event_loop``; every call here sets it to the running loop first.
- A client left open at interpreter exit can crash the process, so ``close()`` always shuts it
  down.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from datetime import timedelta
from typing import Any

import nostr_sdk as _n

from zebra_agent.commons.relay import RelayTransport, RelayUnavailable, SendResult

logger = logging.getLogger(__name__)

NIP44_MAX_PLAINTEXT = 65535


def _keys(secret_hex: str) -> _n.Keys:
    return _n.Keys.parse(secret_hex)


def nip44_encrypt(secret_hex: str, recipient_pubkey: str, plaintext: str) -> str:
    """NIP-44 v2 ciphertext of *plaintext* from *secret_hex* to *recipient_pubkey*.

    Raises:
        ValueError: The plaintext is empty or over the NIP-44 limit (65535 bytes).
    """
    size = len(plaintext.encode("utf-8"))
    if not 1 <= size <= NIP44_MAX_PLAINTEXT:
        raise ValueError(f"NIP-44 plaintext must be 1..{NIP44_MAX_PLAINTEXT} bytes, got {size}")
    return _n.nip44_encrypt(
        _keys(secret_hex).secret_key(),
        _n.PublicKey.parse(recipient_pubkey),
        plaintext,
        _n.Nip44Version.V2,
    )


def nip44_decrypt(secret_hex: str, sender_pubkey: str, ciphertext: str) -> str:
    """Decrypt NIP-44 *ciphertext* sent by *sender_pubkey* to the holder of *secret_hex*.

    Raises:
        ValueError: The ciphertext is malformed or was not encrypted to this key.
    """
    try:
        return _n.nip44_decrypt(
            _keys(secret_hex).secret_key(), _n.PublicKey.parse(sender_pubkey), ciphertext
        )
    except Exception as exc:  # noqa: BLE001 - nostr-sdk raises its own error types
        raise ValueError(f"NIP-44 decryption failed: {exc}") from exc


def _bind_loop() -> None:
    _n.uniffi_set_event_loop(asyncio.get_running_loop())


class NostrSdkTransport(RelayTransport):
    """One relay over nostr-sdk, authenticating (NIP-42) with *auth_secret* when asked.

    strfry asks for AUTH when a NIP-70 protected event arrives; the client answers with the
    device key and resends.
    """

    def __init__(self, url: str, auth_secret: str | None = None, *, timeout: float = 10.0):
        self.url = url
        self.timeout = timeout
        self._auth_secret = auth_secret
        self._client: _n.Client | None = None
        self._relay_url = _n.RelayUrl.parse(url)

    def __repr__(self) -> str:
        return f"NostrSdkTransport({self.url!r})"

    async def _connected(self) -> _n.Client:
        """A connected client. After an outage the old one is dropped and a fresh one built,
        rather than waiting for nostr-sdk's reconnect back-off."""
        _bind_loop()
        if self._client is not None and not await self._is_connected(self._client):
            await self._reset()
        if self._client is None:
            builder = _n.ClientBuilder().connect_timeout(timedelta(seconds=self.timeout))
            if self._auth_secret:
                builder = builder.authenticator(_n.SignerAuthenticator(_keys(self._auth_secret)))
            self._client = builder.build()
            await self._client.add_relay(self._relay_url)
        output = await self._client.try_connect(timedelta(seconds=self.timeout))
        if output.failed or not await self._is_connected(self._client):
            reason = next(iter(output.failed.values()), "not connected")
            await self._reset()
            raise RelayUnavailable(f"{self.url}: {reason}")
        return self._client

    async def _is_connected(self, client: _n.Client) -> bool:
        relay = await client.relay(self._relay_url)
        if relay is None:
            return False
        status = relay.status()
        if inspect.isawaitable(status):
            status = await status
        return status == _n.RelayStatus.CONNECTED

    async def _reset(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.shutdown()
            except Exception as e:  # noqa: BLE001 - a dead client is dropped either way
                logger.debug("nostr-sdk shutdown failed: %s", e)

    async def send(self, event: dict[str, Any]) -> SendResult:
        client = await self._connected()
        sdk_event = _n.Event.from_json(json.dumps(event, ensure_ascii=False))
        out = await client.send_event(
            sdk_event,
            ok_timeout=timedelta(seconds=self.timeout),
            authentication_timeout=timedelta(seconds=self.timeout),
        )
        if out.success:
            return SendResult(True, "")
        message = str(next(iter(out.failed.values()), "no answer"))
        if not SendResult.is_relay_answer(message):
            await self._reset()
            raise RelayUnavailable(f"{self.url}: {message}")
        return SendResult(False, message)

    async def query(self, filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        client = await self._connected()
        sdk_filters = [_n.Filter.from_json(json.dumps(f)) for f in filters]
        events = await client.fetch_events(
            _n.ReqTarget.single(self._relay_url, sdk_filters),
            timeout=timedelta(seconds=self.timeout),
        )
        return [json.loads(e.as_json()) for e in events]

    async def close(self) -> None:
        if self._client is None:
            return
        _bind_loop()
        await self._reset()
