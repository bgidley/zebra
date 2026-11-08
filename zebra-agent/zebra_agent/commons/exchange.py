"""Reading the public Commons and attesting what happened (#232, S5). Off unless built.

``CommonsExchange`` is injected as ``extras["__commons_exchange__"]`` only alongside a
``CommonsPublisher`` (the Commons on, ``ZEBRA_COMMONS_RELAYS`` set, an identity and a device
key). Without it nothing here runs: no fetch, no attestation.

- ``poll()`` (each daemon tick): fetch ``OFFER``s from the canonical relay with their
  publishers' certs, revokes and the operator's receipts, ``intake()`` each (verify, mirror,
  record one ``OfferRecord`` per content hash), then fetch and verify ``ATTEST``s about the
  offers seen and this Zebra's own offers. Nothing is ever imported automatically.
- ``record_import()``: the judged import's outcome (from ``commons_attest_import``) moves the
  offer's status and attests ``adopted`` or the rejecting gate.
- ``after_run()``: ``worked`` / ``failed`` after a run of an adopted offer, only while the
  hash of the current YAML equals the offered hash.

Attestations take only a label, a hash and fixed reasons (``commons/attest.py``): no goal,
output, name or person can reach them.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from zebra_agent.commons.attest import (
    ADOPTED as ATTEST_ADOPTED,
)
from zebra_agent.commons.attest import (
    FAILED,
    REJECTION_LABELS,
    WORKED,
    build_attest,
    verify_attest,
)
from zebra_agent.commons.client import Filter
from zebra_agent.commons.events import Event
from zebra_agent.commons.kinds import (
    ATTEST_KIND,
    DEVICE_CERT_KIND,
    DEVICE_REVOKE_KIND,
    OFFER_KIND,
    RECEIPT_KIND,
    TRUST_KIND,
)
from zebra_agent.commons.offer import offer_input, verify_offer
from zebra_agent.commons.offers import (
    ADOPTED,
    DELISTED,
    IMPORTABLE,
    JUDGING,
    SEEN,
    InvalidOfferTransition,
    OfferRecord,
    OfferStore,
)
from zebra_agent.commons.publisher import CommonsPublisher
from zebra_agent.commons.receipts import receipt_order
from zebra_agent.commons.trust import verify_trust
from zebra_agent.provenance import try_content_sha256

if TYPE_CHECKING:
    from zebra_agent.commons.web_of_trust import WebOfTrust
    from zebra_agent.library import WorkflowLibrary

logger = logging.getLogger(__name__)

EXCHANGE_KEY = "__commons_exchange__"
#: Most events asked for in one fetch.
POLL_LIMIT = 500
_CHUNK = 50


@dataclass(frozen=True)
class IntakeResult:
    """What ``intake`` did with one ``OFFER``: ``reason`` ``ok`` when stored."""

    reason: str
    content_sha256: str | None = None

    @property
    def stored(self) -> bool:
        return self.reason == "ok"


@dataclass
class CommonsExchange:
    """Offers in, attestations out, over this device's ``CommonsPublisher``.

    Attributes:
        publisher: Signs and publishes; its canonical relay is read, its mirror kept
        offers: The offers seen (``WorkflowOfferModel`` on the web)
        since: ``created_at`` of the newest ``OFFER`` read so far (kept in memory)
        attest_since: The same for ``ATTEST``s
        trust: This Zebra's web of trust (#233): ``TRUST`` fetched each poll, experience
            recorded after each of its own attestations; None leaves trust alone
        trust_since: ``created_at`` of the newest ``TRUST`` read so far
    """

    publisher: CommonsPublisher
    offers: OfferStore
    since: int | None = None
    attest_since: int | None = None
    revoke_since: int | None = None
    last_poll: dict[str, int] = field(default_factory=dict)
    trust: WebOfTrust | None = None
    trust_since: int | None = None

    @property
    def zebra_pubkey(self) -> str:
        return self.publisher.zebra_pubkey

    @property
    def mirror(self):
        return self.publisher.mirror

    # -- reading ---------------------------------------------------------------------------

    async def _fetch(self, filters: list[Filter]) -> list[Event]:
        return await self.publisher.canonical.fetch(filters)

    async def _identity(self, zebras: Iterable[str]) -> list[Event]:
        """The certs and revokes the relay holds for *zebras*."""
        zebras = sorted(set(zebras))
        out: list[Event] = []
        for start in range(0, len(zebras), _CHUNK):
            out += await self._fetch(
                [
                    Filter(
                        kinds=(DEVICE_CERT_KIND, DEVICE_REVOKE_KIND),
                        authors=tuple(zebras[start : start + _CHUNK]),
                    )
                ]
            )
        return out

    async def _receipts(self, event_ids: list[str]) -> tuple[dict[str, int] | None, list[Event]]:
        """``event id → seq`` from the operator's receipts, and the receipts themselves.

        None without an operator key: revocation then follows the S1 rule (any revoke wins).
        """
        operator = self.publisher.receipt_pubkey
        if not operator:
            return None, []
        if not event_ids:
            return {}, []
        found: list[Event] = []
        for start in range(0, len(event_ids), _CHUNK):
            found += await self._fetch(
                [
                    Filter(
                        kinds=(RECEIPT_KIND,),
                        authors=(operator,),
                        events=tuple(event_ids[start : start + _CHUNK]),
                    )
                ]
            )
        return receipt_order(found, operator), found

    async def _keep(
        self,
        event: Event,
        chain: list[Event],
        zebra: str,
        receipts: list[Event],
        seq: dict[str, int] | None,
    ) -> None:
        """Mirror *event*, the certs and revokes of *zebra* and their receipts."""
        seq = seq or {}
        mine = [e for e in chain if e.pubkey == zebra]
        kept = {event.id, *(e.id for e in mine)}
        for e in mine:
            await self.mirror.add(e, relay_seq=seq.get(e.id))
        await self.mirror.add(event, relay_seq=seq.get(event.id))
        for receipt in receipts:
            if set(receipt.tag_values("e")) & kept:
                await self.mirror.add(receipt)

    async def intake(
        self,
        event: Event,
        chain: list[Event],
        receipt_seq: dict[str, int] | None = None,
        receipts: list[Event] | None = None,
    ) -> IntakeResult:
        """Verify one ``OFFER`` and record it as ``seen`` once per content hash.

        Reasons: ``ok``, ``own`` (this Zebra's), ``duplicate`` (hash already stored),
        ``delisted`` (the stored ``seen`` offer's own event no longer verifies because
        its device was revoked) and every ``verify_offer`` refusal (``bad_signature``,
        ``no_cert``, ``hash_mismatch``, ...).
        """
        d = event.tag_values("d")
        sha = d[0] if len(d) == 1 else None
        existing = await self.offers.get(sha) if sha else None
        check = verify_offer(event, chain, receipt_seq=receipt_seq)
        if not check.ok:
            # Only the stored row's own event can delist it: anyone can copy the YAML
            # (same ``d`` hash) and sign it with a device they revoked themselves.
            if (
                existing
                and existing.status == SEEN
                and existing.event_id == event.id
                and check.reason in ("revoked", "no_receipt")
            ):
                await self.offers.set_status(existing.content_sha256, DELISTED)
                logger.info("Commons: delisted offer %s… (device revoked)", sha[:12])
                return IntakeResult("delisted", sha)
            logger.info("Commons: refused OFFER %s (%s)", event.id[:12], check.reason)
            return IntakeResult(check.reason, sha)
        if check.zebra_pubkey == self.zebra_pubkey:
            return IntakeResult("own", sha)
        if existing is not None:
            return IntakeResult("duplicate", sha)
        content = check.content
        await self._keep(event, chain, check.zebra_pubkey, receipts or [], receipt_seq)
        await self.offers.add(
            OfferRecord(
                content_sha256=check.content_sha256,
                name=str(content.get("name") or "")[:200],
                summary=str(content.get("summary") or ""),
                use_when=str(content.get("use_when") or ""),
                stats=dict(content.get("stats") or {}),
                publisher_pubkey=check.zebra_pubkey,
                event_id=event.id,
                offered_at=event.created_at,
            )
        )
        logger.info("Commons: saw offer %r (%s…)", content.get("name"), sha[:12])
        return IntakeResult("ok", sha)

    async def poll(self) -> dict[str, int]:
        """One tick: new offers, then attestations. Returns counts by intake reason."""
        events = await self._fetch(
            [Filter(kinds=(OFFER_KIND,), since=self.since, limit=POLL_LIMIT)]
        )
        others = [e for e in events if e.tag_values("zebra") != [self.zebra_pubkey]]
        chain = await self._identity(z for e in others for z in e.tag_values("zebra"))
        seq, receipts = await self._receipts([e.id for e in [*others, *chain]])
        counts: dict[str, int] = {}
        for event in others:
            result = await self.intake(event, chain, seq, receipts)
            counts[result.reason] = counts.get(result.reason, 0) + 1
        if events:
            self.since = max(e.created_at for e in events)
        counts["delisted"] = counts.get("delisted", 0) + await self.check_revocations()
        counts["attestations"] = await self.fetch_attestations()
        if self.trust is not None:
            counts["trust"] = await self.fetch_trust()
        self.last_poll = counts
        return counts

    async def check_revocations(self) -> int:
        """Delist ``seen`` offers whose signing device was revoked since the last check."""
        seen = [r for r in await self.offers.list() if r.status == SEEN]
        publishers = sorted({r.publisher_pubkey for r in seen})
        if not publishers:
            return 0
        revokes = await self._fetch(
            [
                Filter(
                    kinds=(DEVICE_REVOKE_KIND,),
                    authors=tuple(publishers),
                    since=self.revoke_since,
                )
            ]
        )
        new = [e for e in revokes if await self.mirror.get(e.id) is None]
        if revokes:
            self.revoke_since = max(e.created_at for e in revokes)
        revoked_by = {e.pubkey for e in new}
        delisted = 0
        for row in seen:
            if row.publisher_pubkey not in revoked_by:
                continue
            stored = await self.mirror.get(row.event_id)
            if stored is None:
                continue
            chain = await self._identity([row.publisher_pubkey])
            seq, receipts = await self._receipts([stored.event.id, *(e.id for e in chain)])
            if (await self.intake(stored.event, chain, seq, receipts)).reason == "delisted":
                for revoke in new:
                    if revoke.pubkey == row.publisher_pubkey:
                        await self.mirror.add(revoke)
                delisted += 1
        return delisted

    async def fetch_attestations(self) -> int:
        """Verify and mirror new ``ATTEST``s about offers seen and this Zebra's offers."""
        hashes = sorted(
            {r.content_sha256 for r in await self.offers.list()}
            | await self.mirror.offered_hashes(self.zebra_pubkey)
        )
        if not hashes:
            return 0
        found: list[Event] = []
        for start in range(0, len(hashes), _CHUNK):
            found += await self._fetch(
                [
                    Filter(
                        kinds=(ATTEST_KIND,),
                        hashes=tuple(hashes[start : start + _CHUNK]),
                        since=self.attest_since,
                        limit=POLL_LIMIT,
                    )
                ]
            )
        new = [e for e in found if await self.mirror.get(e.id) is None]
        if found:
            self.attest_since = max(e.created_at for e in found)
        if not new:
            return 0
        chain = await self._identity(z for e in new for z in e.tag_values("zebra"))
        seq, receipts = await self._receipts([e.id for e in new])
        kept = 0
        for event in new:
            check = verify_attest(event, chain, receipt_seq=seq)
            if not check.ok:
                logger.info("Commons: refused ATTEST %s (%s)", event.id[:12], check.reason)
                continue
            await self._keep(event, chain, check.zebra_pubkey, receipts, seq)
            kept += 1
        return kept

    async def fetch_trust(self) -> int:
        """Verify, mirror and store new ``TRUST`` events as edges (#233); returns how many
        changed an edge. Recomputes local trust when any did, then publishes this Zebra's own
        pending edges."""
        if self.trust is None:
            return 0
        found = await self._fetch(
            [Filter(kinds=(TRUST_KIND,), since=self.trust_since, limit=POLL_LIMIT)]
        )
        if found:
            self.trust_since = max(e.created_at for e in found)
        new = [e for e in found if await self.mirror.get(e.id) is None]
        changed = 0
        if new:
            chain = await self._identity(z for e in new for z in e.tag_values("zebra"))
            seq, receipts = await self._receipts([e.id for e in new])
            for event in new:
                check = verify_trust(event, chain, receipt_seq=seq)
                if not check.ok:
                    logger.info("Commons: refused TRUST %s (%s)", event.id[:12], check.reason)
                    continue
                await self._keep(event, chain, check.from_pubkey, receipts, seq)
                if await self.trust.ingest(check, event, (seq or {}).get(event.id)):
                    changed += 1
        if changed:
            await self.trust.recompute()
        await self.trust.publish_pending()
        return changed

    # -- importing -------------------------------------------------------------------------

    async def begin_import(self, content_sha256: str) -> str:
        """Move a ``seen`` / ``rejected`` offer to ``judging``; return the import's run input.

        The input (``offer_input``) is the mirrored ``OFFER`` and its publisher's certs and
        revokes: the judge and the adopt step verify it again.

        Raises:
            KeyError: No such offer, or its event is not in the mirror.
            InvalidOfferTransition: The offer is not importable now.
        """
        row = await self.offers.get(content_sha256)
        if row is None:
            raise KeyError(content_sha256)
        if row.status not in IMPORTABLE:
            raise InvalidOfferTransition(f"an offer that is {row.status} cannot be imported")
        stored = await self.mirror.get(row.event_id)
        if stored is None:
            raise KeyError(row.event_id)
        chain = [
            m.event
            for m in await self.mirror.events(pubkey=row.publisher_pubkey)
            if m.event.kind in (DEVICE_CERT_KIND, DEVICE_REVOKE_KIND)
        ]
        await self.offers.set_status(content_sha256, JUDGING)
        return offer_input(stored.event, chain)

    async def abandon_import(self, content_sha256: str) -> None:
        """Back to ``seen`` when an import could not even start."""
        row = await self.offers.get(content_sha256)
        if row is not None and row.status == JUDGING:
            await self.offers.set_status(content_sha256, SEEN)

    # -- attesting -------------------------------------------------------------------------

    async def attest(
        self, label: str, content_sha256: str, *, reason: str | None = None
    ) -> dict[str, Any]:
        """Sign and publish an ``ATTEST`` (``publish_event``: certs, canonical, mirror)."""
        event = build_attest(
            label,
            content_sha256,
            device_secret=self.publisher.device_secret,
            zebra_pubkey=self.zebra_pubkey,
            chain=self.publisher.certs,
            reason=reason,
        )
        result = await self.publisher.publish_event(event)
        logger.info("Commons: attested %s on %s…", label, content_sha256[:12])
        await self._experience(label, content_sha256)
        return {**result, "label": label}

    async def _experience(self, label: str, content_sha256: str) -> None:
        """Let this attestation move this Zebra's trust in the offer's publisher (#233)."""
        if self.trust is None:
            return
        row = await self.offers.get(content_sha256)
        if row is None:
            return
        try:
            await self.trust.record_experience(row.publisher_pubkey, label)
        except Exception:  # noqa: BLE001 - trust never breaks an attestation
            logger.exception("Commons: recording experience of %s failed", label)

    async def record_import(
        self,
        content_sha256: str,
        *,
        status: str,
        label: str | None,
        reason: str | None = None,
        judgement: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Record a judged import of an offer and attest *label* (None: nothing public).

        The offer row moves to *status* with the local *judgement* (an illegal move is
        logged, never raised); returns the attestation's publish result, or None.
        """
        if await self.offers.get(content_sha256) is not None:
            try:
                await self.offers.set_status(content_sha256, status, judgement or {})
            except InvalidOfferTransition as e:
                logger.warning("Commons: offer %s…: %s", content_sha256[:12], e)
        if label is None:
            return None
        if label != ATTEST_ADOPTED and label not in REJECTION_LABELS:
            raise ValueError(f"{label} is not an import outcome")
        return await self.attest(label, content_sha256, reason=reason)

    async def after_run(
        self, library: WorkflowLibrary, workflow_name: str, success: bool
    ) -> dict[str, Any] | None:
        """Attest ``worked`` / ``failed`` after a run of an adopted offer, or do nothing.

        Only when the workflow was adopted, its offer row is ``adopted`` and the hash of its
        current YAML equals the offered hash: a locally modified copy never attests against
        the publisher. Takes no goal or output, so neither can reach the attestation.
        """
        block = library.commons_block(workflow_name) if workflow_name else None
        if not block or not block.get("adopted_at"):
            return None
        sha = block.get("content_sha256")
        row = await self.offers.get(sha) if isinstance(sha, str) else None
        if row is None or row.status != ADOPTED:
            return None
        try:
            current = library.get_workflow_yaml(workflow_name)
        except Exception:  # noqa: BLE001 - an unreadable workflow never attests
            return None
        actual, _ = try_content_sha256(current)
        if actual != sha:
            logger.info(
                "Commons: %r changed locally (%s… ≠ offered %s…); no attestation",
                workflow_name,
                (actual or "-")[:12],
                sha[:12],
            )
            return None
        return await self.attest(WORKED if success else FAILED, sha)


# -- read model ------------------------------------------------------------------------------


def attestation_summary(
    events: Iterable[Event], *, exclude_zebra: str | None = None
) -> dict[str, dict[str, Any]]:
    """Per content hash: ``adopted`` / ``rejected`` (distinct Zebras), ``worked`` / ``failed``
    (runs) and ``items`` (label, Zebra, reason, time), from verified mirrored ``ATTEST``s.

    *exclude_zebra* leaves out one Zebra's own attestations (on its own offers).
    """
    out: dict[str, dict[str, Any]] = {}
    seen: dict[str, dict[str, set[str]]] = {}
    for event in events:
        if event.kind != ATTEST_KIND:
            continue
        zebras, xs, labels = event.tag_values("zebra"), event.tag_values("x"), event.tag_values("l")
        if len(zebras) != 1 or len(xs) != 1 or len(labels) != 1 or zebras[0] == exclude_zebra:
            continue
        zebra, sha, label = zebras[0], xs[0], labels[0]
        row = out.setdefault(
            sha, {"adopted": 0, "rejected": 0, "worked": 0, "failed": 0, "items": []}
        )
        groups = seen.setdefault(sha, {"adopted": set(), "rejected": set()})
        if label == ATTEST_ADOPTED:
            groups["adopted"].add(zebra)
        elif label in REJECTION_LABELS:
            groups["rejected"].add(zebra)
        elif label in (WORKED, FAILED):
            row[label] += 1
        content = event.json_content() or {}
        row["items"].append(
            {
                "label": label,
                "zebra_pubkey": zebra,
                "reason": content.get("reason"),
                "created_at": event.created_at,
            }
        )
    for sha, groups in seen.items():
        out[sha]["adopted"] = len(groups["adopted"])
        out[sha]["rejected"] = len(groups["rejected"])
        out[sha]["items"].sort(key=lambda i: i["created_at"], reverse=True)
    return out


def empty_summary() -> dict[str, Any]:
    return {"adopted": 0, "rejected": 0, "worked": 0, "failed": 0, "items": []}


async def own_offers(mirror, zebra_pubkey: str) -> list[dict[str, Any]]:
    """This Zebra's published offers (newest first) with attestations from other Zebras."""
    rows = await mirror.events(kind=OFFER_KIND)
    attests = attestation_summary(
        [m.event for m in await mirror.events(kind=ATTEST_KIND)], exclude_zebra=zebra_pubkey
    )
    latest: dict[str, Event] = {}
    for m in rows:
        if m.event.tag_values("zebra") != [zebra_pubkey]:
            continue
        sha = (m.event.tag_values("d") or [""])[0]
        if sha not in latest or m.event.created_at > latest[sha].created_at:
            latest[sha] = m.event
    out = []
    for sha, event in sorted(latest.items(), key=lambda kv: kv[1].created_at, reverse=True):
        content = event.json_content() or {}
        out.append(
            {
                "content_sha256": sha,
                "name": content.get("name") or "",
                "summary": content.get("summary") or "",
                "stats": content.get("stats") or {},
                "offered_at": event.created_at,
                "attestations": attests.get(sha, empty_summary()),
            }
        )
    return out
