"""Relay receipts: the canonical order of events on a Zebra relay (#246, S3b-2; #231).

A ``RECEIPT`` is signed by the relay operator key (``SYNC_RECEIPT_PUBKEY``) and says "event
``event_id`` was stored as number ``seq``". Readers order revocations by it, never by the
signer's ``created_at``, which a stolen device could backdate.

The relay's write-policy plugin (``deploy/podman/sync-relay/write_policy.py``) assigns ``seq``
in the order it accepts events and appends one line per event to a journal. ``ReceiptSigner``
(run as ``python -m zebra_agent.commons.receipts``, a sidecar next to strfry) signs a receipt
for each journal line and publishes it. Its secret comes only from
``ZEBRA_SYNC_OPERATOR_SECRET`` (hex or ``nsec``); it is never logged. The public Commons
relay (#231, ``deploy/podman/commons-relay/``) runs the same sidecar with
``--secret-env ZEBRA_COMMONS_OPERATOR_SECRET`` and its own operator key.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from zebra_agent.commons import keys
from zebra_agent.commons.events import (
    COMMONS_TAG,
    PROTOCOL_VERSION_TAG,
    Event,
    sign_event,
    verify_event,
)
from zebra_agent.commons.kinds import RECEIPT_KIND

logger = logging.getLogger(__name__)

OPERATOR_SECRET_ENV = "ZEBRA_SYNC_OPERATOR_SECRET"


def make_receipt(
    operator_secret: str, seq: int, event_id: str, kind: int, created_at: int | None = None
) -> Event:
    """Sign ``RECEIPT {seq, event_id}`` for a stored event of *kind*."""
    content = json.dumps({"seq": int(seq), "event_id": event_id}, separators=(",", ":"))
    tags = [
        ["e", event_id],
        ["k", str(int(kind))],
        ["seq", str(int(seq))],
        COMMONS_TAG,
        PROTOCOL_VERSION_TAG,
    ]
    return sign_event(operator_secret, RECEIPT_KIND, tags, content, created_at)


def parse_receipt(event: Event, operator_pubkey: str) -> tuple[str, int] | None:
    """``(event_id, seq)`` of a valid receipt from *operator_pubkey*, else None.

    Valid means: kind ``RECEIPT``, signed by the operator, content and tags agree.
    """
    if event.kind != RECEIPT_KIND or event.pubkey != operator_pubkey:
        return None
    if not verify_event(event):
        return None
    content = event.json_content() or {}
    seq, event_id = content.get("seq"), content.get("event_id")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        return None
    if not isinstance(event_id, str) or event.tag_values("e") != [event_id]:
        return None
    if event.tag_values("seq") != [str(seq)]:
        return None
    return event_id, seq


def receipt_order(events: Iterable[Event], operator_pubkey: str) -> dict[str, int]:
    """Event id → ``seq`` from the valid receipts among *events* (lowest ``seq`` wins)."""
    order: dict[str, int] = {}
    for event in events:
        parsed = parse_receipt(event, operator_pubkey)
        if parsed is None:
            continue
        event_id, seq = parsed
        if event_id not in order or seq < order[event_id]:
            order[event_id] = seq
    return order


def write_secret_file(path: Path, text: str) -> None:
    """Create *path* with mode 0600 and write *text*; never overwrite an existing file.

    Raises:
        FileExistsError: If *path* already exists.
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


def operator_secret_from_env(
    env: dict[str, str] | None = None, name: str = OPERATOR_SECRET_ENV
) -> str:
    """The operator secret (hex or ``nsec``) from the variable *name*.

    ``ZEBRA_SYNC_OPERATOR_SECRET`` for the private sync relay; the public Commons relay's
    sidecar passes ``--secret-env ZEBRA_COMMONS_OPERATOR_SECRET`` (#231).

    Raises:
        ValueError: Unset or not a valid secret key.
    """
    raw = ((os.environ if env is None else env).get(name) or "").strip()
    if not raw:
        raise ValueError(f"{name} is not set")
    secret = keys.nsec_decode(raw) if raw.startswith("nsec1") else raw
    keys.public_key(secret)  # raises InvalidKeyError (a ValueError) when malformed
    return secret


class ReceiptSigner:
    """Signs and publishes a receipt for every line of the relay plugin's journal.

    ``state_path`` holds the last ``seq`` published, so a restart resumes and an outage only
    delays receipts: the order was fixed when the plugin journalled each event.
    """

    def __init__(self, journal_path: Path, state_path: Path, client: Any, operator_secret: str):
        self.journal_path = Path(journal_path)
        self.state_path = Path(state_path)
        self.client = client  # a CommonsClient (publish only)
        self._secret = operator_secret

    def __repr__(self) -> str:
        return f"ReceiptSigner({str(self.journal_path)!r})"

    @property
    def operator_pubkey(self) -> str:
        return keys.public_key(self._secret)

    def last_seq(self) -> int:
        try:
            return int(json.loads(self.state_path.read_text())["last_seq"])
        except (OSError, ValueError, KeyError, TypeError):
            return 0

    def _save(self, seq: int) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"last_seq": seq}))
        os.replace(tmp, self.state_path)

    def pending(self) -> list[dict[str, Any]]:
        """Journal entries after the last published ``seq``, in order."""
        last = self.last_seq()
        if not self.journal_path.exists():
            return []
        out = []
        for line in self.journal_path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
                seq, event_id, kind = int(entry["seq"]), str(entry["id"]), int(entry["kind"])
            except (ValueError, KeyError, TypeError):
                continue
            if seq > last:
                out.append({"seq": seq, "id": event_id, "kind": kind})
        return sorted(out, key=lambda e: e["seq"])

    async def run_once(self) -> int:
        """Publish receipts for pending entries; returns how many. Stops at the first failure."""
        published = 0
        for entry in self.pending():
            receipt = make_receipt(self._secret, entry["seq"], entry["id"], entry["kind"])
            try:
                await self.client.publish(receipt)
            except Exception as e:  # noqa: BLE001 - retried on the next pass
                logger.warning("Receipt %d not published yet: %s", entry["seq"], e)
                break
            self._save(entry["seq"])
            published += 1
        return published

    async def run(self, interval: float = 1.0) -> None:
        logger.info("Receipt signer %s… watching %s", self.operator_pubkey[:16], self.journal_path)
        while True:
            try:
                count = await self.run_once()
                if count:
                    logger.info("Published %d receipt(s), last seq %d", count, self.last_seq())
            except Exception:  # noqa: BLE001 - the sidecar keeps running
                logger.exception("Receipt signer pass failed")
            await asyncio.sleep(interval)


def main(argv: list[str] | None = None) -> None:
    """The receipt sidecar: ``python -m zebra_agent.commons.receipts``."""
    from zebra_agent.commons.nostr import NostrSdkTransport
    from zebra_agent.commons.relay import RelayCommonsClient

    parser = argparse.ArgumentParser(description="Sign RECEIPTs for a Zebra relay")
    parser.add_argument("--relay", default=os.environ.get("ZEBRA_SYNC_RELAY_LOCAL"))
    parser.add_argument(
        "--journal", default=os.environ.get("ZEBRA_SYNC_JOURNAL", "/receipts/journal.jsonl")
    )
    parser.add_argument(
        "--state", default=os.environ.get("ZEBRA_SYNC_RECEIPT_STATE", "/receipts/signer.json")
    )
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument(
        "--secret-env",
        default=OPERATOR_SECRET_ENV,
        help="variable holding the operator secret (ZEBRA_COMMONS_OPERATOR_SECRET for the "
        "public Commons relay, #231)",
    )
    parser.add_argument(
        "--keygen",
        action="store_true",
        help="write a new operator key to --out (0600, never overwritten), print its public key",
    )
    parser.add_argument("--out", help="--keygen: new env file for the operator secret")
    args = parser.parse_args(argv)
    if args.keygen:
        if not args.out:
            parser.error("--keygen needs --out FILE: the secret is never printed")
        secret = keys.generate_secret_key()
        try:
            write_secret_file(Path(args.out), f"{args.secret_env}={keys.nsec_encode(secret)}\n")
        except FileExistsError:
            parser.error(f"{args.out} already exists; refusing to overwrite an operator key")
        pubkey_env = args.secret_env.replace("OPERATOR_SECRET", "RECEIPT_PUBKEY")
        print(f"Wrote {args.secret_env} to {args.out} (mode 600)")
        print(f"{pubkey_env}={keys.public_key(secret)}")
        return
    if not args.relay:
        parser.error("--relay or ZEBRA_SYNC_RELAY_LOCAL is required")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(asctime)s %(message)s")
    secret = operator_secret_from_env(name=args.secret_env)
    client = RelayCommonsClient(NostrSdkTransport(args.relay))
    signer = ReceiptSigner(Path(args.journal), Path(args.state), client, secret)
    asyncio.run(signer.run(args.interval))


if __name__ == "__main__":
    main()
