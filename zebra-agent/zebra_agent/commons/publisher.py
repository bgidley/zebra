"""Publishing to the public Commons relays (#231, S4). Off unless ``COMMONS_RELAYS`` is set.

``CommonsPublisher`` is injected into the engine as ``extras["__commons_publisher__"]`` only
when the Commons is on, ``ZEBRA_COMMONS_RELAYS`` is set and this device has a Zebra identity
and device key (``zebra_agent_web.api.commons_publish``). The *Commons Offer* workflow's
``commons_publish`` step is its only caller.

- The **canonical** relay is the first of ``COMMONS_RELAYS``; its operator key
  (``COMMONS_RECEIPT_PUBKEY``) is the only one trusted for ``RECEIPT``s. The others are
  **mirrors**, written best effort.
- Every client is a public ``CommonsClient`` (``private=False``), so the hard filter in
  ``CommonsClient.check_publish`` refuses anything but the public kinds, and ``SKILL`` always.
- Before an ``OFFER`` it publishes the signing device's ``DEVICE_CERT`` and this Zebra's
  ``DEVICE_REVOKE``s, so a reader can attribute it. Other devices' certs stay private.
- Every event it publishes, and every receipt it relies on, goes into the local mirror.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from zebra_agent.commons import keys
from zebra_agent.commons.client import CommonsClient, Filter
from zebra_agent.commons.events import Event
from zebra_agent.commons.identity import parse_cert, verify_device_chain
from zebra_agent.commons.kinds import (
    ATTEST_KIND,
    DEVICE_CERT_KIND,
    DEVICE_REVOKE_KIND,
    OFFER_KIND,
    RECEIPT_KIND,
    TRUST_KIND,
)
from zebra_agent.commons.mirror import CommonsMirror
from zebra_agent.commons.offer import (
    OfferRefused,
    build_offer,
    public_parent,
    verify_offer,
)
from zebra_agent.commons.receipts import receipt_order

logger = logging.getLogger(__name__)

PUBLISHER_KEY = "__commons_publisher__"


@dataclass
class CommonsPublisher:
    """This device's publisher to the public Commons.

    Attributes:
        canonical: The canonical public relay (receipts); ``private`` must be False
        mirrors: Other public relays, written best effort
        device_secret: This device's secret key (never logged)
        zebra_pubkey: This device's Zebra key
        certs: The ``DEVICE_CERT`` / ``DEVICE_REVOKE`` events of this Zebra held here
        mirror: The local mirror of Commons events
        sphere: This device's sphere; ``observed`` whether it is managed by someone else
        receipt_pubkey: The canonical relay's operator key (``COMMONS_RECEIPT_PUBKEY``)
        receipt_wait: Seconds ``publish_offer`` waits for the receipt before moving on
    """

    canonical: CommonsClient
    device_secret: str = field(repr=False)
    zebra_pubkey: str
    mirror: CommonsMirror
    mirrors: list[CommonsClient] = field(default_factory=list)
    certs: list[Event] = field(default_factory=list)
    sphere: str = "home"
    observed: bool = False
    receipt_pubkey: str | None = None
    receipt_wait: float = 5.0
    receipt_poll: float = 0.25

    def __post_init__(self) -> None:
        for client in (self.canonical, *self.mirrors):
            if client.private:
                raise ValueError("Commons relays must be public clients (private=False)")

    @property
    def device_pubkey(self) -> str:
        return keys.public_key(self.device_secret)

    # -- spheres -------------------------------------------------------------------------

    def spheres(self) -> dict[str, bool]:
        """Sphere → observed, over this device and the devices whose chain verifies."""
        out: dict[str, bool] = {self.sphere: self.observed}
        for event in self.certs:
            cert = parse_cert(event) if event.kind == DEVICE_CERT_KIND else None
            if cert is None or cert.zebra_pubkey != self.zebra_pubkey:
                continue
            if verify_device_chain(cert.device_pubkey, self.zebra_pubkey, self.certs).ok:
                out[cert.sphere] = out.get(cert.sphere, False) or cert.observed
        return out

    def is_observed(self, sphere: str) -> bool:
        """Whether *sphere* is observed; a sphere no cert describes counts as observed."""
        return self.spheres().get(sphere, True)

    def observed_taint(self, block: Mapping[str, Any] | None) -> list[str]:
        """The observed (or unknown) spheres in the block's ``tainted_by``."""
        tainted = (block or {}).get("tainted_by") or []
        return sorted({s for s in tainted if not isinstance(s, str) or self.is_observed(s)})

    # -- offers --------------------------------------------------------------------------

    async def offered_hashes(self) -> set[str]:
        """Content hashes this Zebra has published an ``OFFER`` of (from the mirror)."""
        return await self.mirror.offered_hashes(self.zebra_pubkey)

    async def public_hashes(self) -> set[str]:
        """Content hashes publicly offered by any Zebra (``CommonsMirror.public_hashes``)."""
        return await self.mirror.public_hashes()

    def identity_events(self) -> list[Event]:
        """The signing device's current cert and this Zebra's revokes (what readers need)."""
        mine = verify_device_chain(self.device_pubkey, self.zebra_pubkey, self.certs)
        out = [mine.cert.event] if mine.ok and mine.cert is not None else []
        out += [
            e for e in self.certs if e.kind == DEVICE_REVOKE_KIND and e.pubkey == self.zebra_pubkey
        ]
        return out

    async def build(self, content: Mapping[str, Any], block: Mapping[str, Any] | None) -> Event:
        """Sign an ``OFFER`` (``parent`` only if publicly offered) and check it verifies."""
        parent = public_parent(block, await self.public_hashes())
        event = build_offer(
            content,
            device_secret=self.device_secret,
            zebra_pubkey=self.zebra_pubkey,
            chain=self.certs,
            parent=parent,
        )
        check = verify_offer(event, self.certs, expected_zebra=self.zebra_pubkey)
        if not check.ok:  # pragma: no cover - build_offer guards every reason
            raise OfferRefused(f"the offer failed its own verification ({check.reason})")
        return event

    async def publish_offer(
        self, content: Mapping[str, Any], block: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        """Publish an ``OFFER`` to the canonical relay and the mirrors.

        Returns ``{event_id, content_sha256, parent, receipt_seq, mirrors}``; ``receipt_seq``
        is None when no receipt arrived within ``receipt_wait`` (``refresh_receipts`` picks it
        up later). Raises ``OfferRefused`` when the offer cannot be built and any
        ``PublishRefused`` / ``RelayUnavailable`` from the canonical relay: nothing counts as
        offered until the canonical relay has it.
        """
        event = await self.build(content, block)
        result = await self.publish_event(event)
        logger.info(
            "Commons: published OFFER %s of %r (%s…)",
            event.id[:12],
            content.get("name"),
            event.tag_values("d")[0][:12],
        )
        parents = event.tag_values("parent")
        return {
            **result,
            "content_sha256": event.tag_values("d")[0],
            "parent": parents[0] if parents else None,
        }

    async def publish_event(self, event: Event) -> dict[str, Any]:
        """Publish a signed public event (``OFFER``, ``ATTEST``, ``TRUST``) like every other.

        The signing device's cert and this Zebra's revokes first, then the event, to the
        canonical relay (errors propagate: nothing counts as published until it has it), into
        the local mirror, then to the mirrors best effort; then a short wait for the receipt.
        Returns ``{event_id, receipt_seq, mirrors}``.
        """
        identity = self.identity_events()
        for cert in identity:
            await self.canonical.publish(cert)
        await self.canonical.publish(event)
        for cert in identity:
            await self.mirror.add(cert)
        await self.mirror.add(event)
        mirrors: dict[str, str] = {}
        for client in self.mirrors:
            label = repr(client)
            try:
                for cert in identity:
                    await client.publish(cert)
                await client.publish(event)
                mirrors[label] = "ok"
            except Exception as e:  # noqa: BLE001 - mirrors are best effort
                logger.warning("Commons: mirror %s did not take %s: %s", label, event.id[:12], e)
                mirrors[label] = str(e)[:200]
        seq = await self.wait_for_receipt(event.id)
        return {"event_id": event.id, "receipt_seq": seq, "mirrors": mirrors}

    async def _fetch_receipts(self, event_ids: list[str]) -> dict[str, int]:
        if not self.receipt_pubkey or not event_ids:
            return {}
        found = await self.canonical.fetch(
            [Filter(kinds=(RECEIPT_KIND,), authors=(self.receipt_pubkey,), events=tuple(event_ids))]
        )
        order = receipt_order(found, self.receipt_pubkey)
        for receipt in found:
            if receipt.tag_values("e") and receipt.tag_values("e")[0] in order:
                await self.mirror.add(receipt)
        return order

    async def wait_for_receipt(self, event_id: str) -> int | None:
        """The canonical relay's receipt ``seq`` for *event_id*, waiting up to ``receipt_wait``."""
        if not self.receipt_pubkey:
            return None
        deadline = time.monotonic() + self.receipt_wait
        while True:
            try:
                order = await self._fetch_receipts([event_id])
            except Exception as e:  # noqa: BLE001 - the receipt can come later
                logger.info("Commons: receipt lookup failed: %s", e)
                order = {}
            if event_id in order:
                return order[event_id]
            if time.monotonic() >= deadline:
                logger.info("Commons: no receipt yet for %s", event_id[:12])
                return None
            await asyncio.sleep(self.receipt_poll)

    async def refresh_receipts(self) -> int:
        """Fetch receipts for mirrored events that have none yet; returns how many."""
        if not self.receipt_pubkey:
            return 0
        have = await self.mirror.receipt_seq(self.receipt_pubkey)
        rows = await self.mirror.events()
        ours = [
            m.event.id
            for m in rows
            if m.event.kind
            in (OFFER_KIND, ATTEST_KIND, TRUST_KIND, DEVICE_CERT_KIND, DEVICE_REVOKE_KIND)
            and m.event.id not in have
        ]
        found = 0
        for start in range(0, len(ours), 50):
            found += len(await self._fetch_receipts(ours[start : start + 50]))
        return found

    async def close(self) -> None:
        for client in (self.canonical, *self.mirrors):
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                logger.debug("Commons: closing %r failed", client, exc_info=True)
