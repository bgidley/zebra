#!/usr/bin/env python3
"""strfry write policy for the public Zebra Commons relay (#231, S4).

Runs inside the strfry container (Python 3.11, standard library only). strfry passes one JSON
request per line on stdin and reads one JSON answer per line on stdout. strfry has already
checked every event's id and signature, so ``pubkey`` is the real author.

Open to any Zebra (no allow-list, no NIP-42), but accepts only Zebra Commons events (tag
``["t","zebra-commons"]``) of the public kinds:

- ``RECEIPT`` only from the relay operator key (``policy.json``), not journalled;
- ``OFFER`` with one ``d`` equal to one ``x`` (a 64-hex content hash) and one ``zebra`` key;
- ``DEVICE_CERT`` / ``DEVICE_REVOKE`` / ``ATTEST`` / ``TRUST`` / ``GRANT`` / ``TRADE`` /
  ``OUTCOME``.

Never ``SKILL`` (private relay only) or any other kind, and never a NIP-70 protected event
(nothing here is private). Every accepted event except receipts gets the next ``seq`` and a line
in the journal (written and fsynced before strfry is told to accept); the receipt sidecar signs a
``RECEIPT`` per line. ``policy.json`` (``{"operator_pubkey": "<hex>"}``) is re-read when it
changes; without it receipts are refused. Anything unreadable fails closed (rejects).

The kind numbers repeat ``zebra_agent/commons/kinds.py``; ``test_commons_public_relay.py`` keeps
them equal.

Environment: ``ZEBRA_COMMONS_POLICY`` (default ``/etc/zebra-commons/policy.json``),
``ZEBRA_COMMONS_JOURNAL`` (default ``/receipts/journal.jsonl``).
"""

from __future__ import annotations

import json
import os
import sys
import time

DEVICE_CERT_KIND = 30228
DEVICE_REVOKE_KIND = 1228
RECEIPT_KIND = 1246
OFFER_KIND = 30231
ATTEST_KIND = 1232
TRUST_KIND = 30233
GRANT_KIND = 1234
TRADE_KIND = 1235
OUTCOME_KIND = 1236
SKILL_KIND = 4236
PUBLIC_KINDS = frozenset(
    {
        OFFER_KIND,
        ATTEST_KIND,
        TRUST_KIND,
        GRANT_KIND,
        TRADE_KIND,
        OUTCOME_KIND,
        RECEIPT_KIND,
        DEVICE_CERT_KIND,
        DEVICE_REVOKE_KIND,
    }
)
COMMONS_TAG = ["t", "zebra-commons"]
PROTECTED_TAG = ["-"]
HEX = set("0123456789abcdef")


def _is_key(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX


def _tag_values(tags: list, name: str) -> list:
    return [t[1] for t in tags if isinstance(t, list) and len(t) >= 2 and t[0] == name]


def _log(message: str) -> None:
    print(f"zebra-commons-policy: {message}", file=sys.stderr, flush=True)


class Policy:
    """The public relay's kind filter and receipt journal."""

    def __init__(self, policy_path: str, journal_path: str):
        self.policy_path = policy_path
        self.journal_path = journal_path
        self.operator = ""
        self._mtime: float | None = None
        self.seq = 0
        self.seen: set[str] = set()
        self._load_policy()
        self._replay()

    def _load_policy(self) -> None:
        try:
            mtime = os.stat(self.policy_path).st_mtime
        except OSError:
            if self._mtime is not None or not self.operator:
                _log(f"no policy file at {self.policy_path}: receipts are refused")
            self.operator, self._mtime = "", None
            return
        if mtime == self._mtime:
            return
        try:
            with open(self.policy_path, encoding="utf-8") as fh:
                operator = str(json.load(fh).get("operator_pubkey") or "").lower()
        except (OSError, ValueError, AttributeError) as e:
            _log(f"unreadable policy file ({e}): receipts are refused")
            self.operator, self._mtime = "", mtime
            return
        self.operator = operator if _is_key(operator) else ""
        self._mtime = mtime
        _log(f"operator key {'set' if self.operator else 'unset'}")

    def _replay(self) -> None:
        if not os.path.exists(self.journal_path):
            return
        with open(self.journal_path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    entry = json.loads(line)
                    self.seq = max(self.seq, int(entry["seq"]))
                    self.seen.add(str(entry["id"]))
                except (ValueError, KeyError, TypeError):
                    continue

    def _journal(self, event: dict) -> None:
        if event["id"] in self.seen:
            return  # a resend: keep its first seq
        entry = {
            "seq": self.seq + 1,
            "id": event["id"],
            "kind": event["kind"],
            "pubkey": event["pubkey"],
            "created_at": event.get("created_at", 0),
            "at": int(time.time()),
        }
        os.makedirs(os.path.dirname(self.journal_path) or ".", exist_ok=True)
        with open(self.journal_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, separators=(",", ":")) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self.seq += 1
        self.seen.add(event["id"])

    def decide(self, request: dict) -> tuple[str, str]:
        """``(action, message)`` for one ``new`` request; journals what it accepts."""
        self._load_policy()
        event = request.get("event") or {}
        tags = event.get("tags") or []
        kind = event.get("kind")
        pubkey = str(event.get("pubkey") or "")
        if COMMONS_TAG not in tags:
            return "reject", "blocked: not a Zebra Commons event"
        if kind == SKILL_KIND:
            return "reject", "blocked: SKILL events go only to a private sync relay"
        if kind not in PUBLIC_KINDS:
            return "reject", "blocked: kind not accepted on this relay"
        if PROTECTED_TAG in tags:
            return "reject", "blocked: protected (NIP-70) events are not accepted here"
        if kind == RECEIPT_KIND:
            if self.operator and pubkey == self.operator:
                return "accept", ""
            return "reject", "blocked: receipts come only from the relay operator"
        if kind == OFFER_KIND:
            d, x = _tag_values(tags, "d"), _tag_values(tags, "x")
            zebra = _tag_values(tags, "zebra")
            if len(d) != 1 or d != x or not _is_key(d[0]) or len(zebra) != 1:
                return "reject", "invalid: malformed OFFER"
            if not _is_key(zebra[0]):
                return "reject", "invalid: malformed OFFER"
        self._journal(event)
        return "accept", ""


def main() -> None:
    policy = Policy(
        os.environ.get("ZEBRA_COMMONS_POLICY", "/etc/zebra-commons/policy.json"),
        os.environ.get("ZEBRA_COMMONS_JOURNAL", "/receipts/journal.jsonl"),
    )
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except ValueError:
            _log("unreadable request")
            continue
        if request.get("type") != "new":
            continue  # lookback / other request types need no answer
        event_id = (request.get("event") or {}).get("id")
        if not event_id:
            continue
        try:
            action, message = policy.decide(request)
        except Exception as e:  # noqa: BLE001 - never crash the relay; fail closed
            _log(f"error deciding {event_id}: {e}")
            action, message = "reject", "error: write policy failed"
        answer = {"id": event_id, "action": action}
        if message:
            answer["msg"] = message
        print(json.dumps(answer, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
