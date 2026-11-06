#!/usr/bin/env python3
"""strfry write policy for Zebra's private sync relay (#246, S3b-2).

Runs inside the strfry container (Python 3.11, standard library only). strfry passes one JSON
request per line on stdin and reads one JSON answer per line on stdout. strfry has already
checked every event's id and signature, so ``pubkey`` is the real author.

Accepts only Zebra Commons events (tag ``["t","zebra-commons"]``) of these kinds:

- ``DEVICE_CERT`` / ``DEVICE_REVOKE`` authored by a registered Zebra key (``allowlist.json``);
- ``SKILL`` that is NIP-70 protected, published by a connection authenticated (NIP-42) as its
  author, and authored by a device with a valid, unexpired, unrevoked cert from a registered
  Zebra key;
- ``RECEIPT`` authored by the relay operator key (not journalled).

Every accepted event except receipts gets the next ``seq`` and a line in the journal (written and
fsynced before strfry is told to accept). The receipt sidecar signs a ``RECEIPT`` per line. The
cert/revoke state is rebuilt from the journal at start; ``allowlist.json`` is re-read when it
changes. Anything unreadable fails closed (rejects).

Environment: ``ZEBRA_SYNC_ALLOWLIST`` (default ``/etc/zebra-sync/allowlist.json``),
``ZEBRA_SYNC_JOURNAL`` (default ``/receipts/journal.jsonl``).
"""

from __future__ import annotations

import json
import os
import sys
import time

SKILL_KIND = 4236
DEVICE_CERT_KIND = 30228
DEVICE_REVOKE_KIND = 1228
RECEIPT_KIND = 1246
COMMONS_TAG = ["t", "zebra-commons"]
PROTECTED_TAG = ["-"]
HEX = set("0123456789abcdef")


def _is_key(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX


def _tag_values(tags: list, name: str) -> list:
    return [t[1] for t in tags if isinstance(t, list) and len(t) >= 2 and t[0] == name]


def _log(message: str) -> None:
    print(f"zebra-sync-policy: {message}", file=sys.stderr, flush=True)


class Policy:
    """The relay's allow-list and receipt journal."""

    def __init__(self, allowlist_path: str, journal_path: str):
        self.allowlist_path = allowlist_path
        self.journal_path = journal_path
        self.zebras: set[str] = set()
        self.operator = ""
        self._allow_mtime: float | None = None
        self.seq = 0
        self.seen: set[str] = set()
        self.certs: dict[str, dict] = {}  # device -> {zebra, created_at, expires_at}
        self.revoked: set[tuple[str, str]] = set()  # (zebra, device)
        self._load_allowlist()
        self._replay()

    # -- state -----------------------------------------------------------------------

    def _load_allowlist(self) -> None:
        try:
            mtime = os.stat(self.allowlist_path).st_mtime
        except OSError:
            if self._allow_mtime is not None or not self.zebras:
                _log(f"no allow-list at {self.allowlist_path}: rejecting everything")
            self.zebras, self.operator, self._allow_mtime = set(), "", None
            return
        if mtime == self._allow_mtime:
            return
        try:
            with open(self.allowlist_path, encoding="utf-8") as fh:
                data = json.load(fh)
            zebras = {k.lower() for k in data.get("zebra_pubkeys") or [] if _is_key(k.lower())}
            operator = str(data.get("operator_pubkey") or "").lower()
        except (OSError, ValueError, AttributeError) as e:
            _log(f"unreadable allow-list ({e}): rejecting everything")
            self.zebras, self.operator, self._allow_mtime = set(), "", mtime
            return
        self.zebras = zebras
        self.operator = operator if _is_key(operator) else ""
        self._allow_mtime = mtime
        operator_state = "set" if self.operator else "unset"
        _log(f"allow-list: {len(zebras)} Zebra key(s), operator {operator_state}")

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
                self._learn(entry)

    def _learn(self, entry: dict) -> None:
        device = entry.get("device")
        if not _is_key(device):
            return
        if entry.get("kind") == DEVICE_CERT_KIND:
            current = self.certs.get(device)
            if current is None or entry.get("created_at", 0) >= current["created_at"]:
                self.certs[device] = {
                    "zebra": entry.get("pubkey"),
                    "created_at": entry.get("created_at", 0),
                    "expires_at": entry.get("expires_at"),
                }
        elif entry.get("kind") == DEVICE_REVOKE_KIND:
            self.revoked.add((entry.get("pubkey"), device))

    def device_ok(self, device: str, now: int) -> bool:
        cert = self.certs.get(device)
        if cert is None or cert["zebra"] not in self.zebras:
            return False
        if (cert["zebra"], device) in self.revoked:
            return False
        expires = cert.get("expires_at")
        return expires is None or expires > now

    def _journal(self, event: dict, device: str | None, expires_at: int | None) -> None:
        if event["id"] in self.seen:
            return  # a resend: keep its first seq
        entry = {
            "seq": self.seq + 1,
            "id": event["id"],
            "kind": event["kind"],
            "pubkey": event["pubkey"],
            "device": device,
            "created_at": event.get("created_at", 0),
            "expires_at": expires_at,
            "at": int(time.time()),
        }
        os.makedirs(os.path.dirname(self.journal_path) or ".", exist_ok=True)
        with open(self.journal_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, separators=(",", ":")) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self.seq += 1
        self.seen.add(event["id"])
        self._learn(entry)

    # -- decisions -------------------------------------------------------------------

    def decide(self, request: dict) -> tuple[str, str]:
        """``(action, message)`` for one ``new`` request; journals what it accepts."""
        self._load_allowlist()
        event = request.get("event") or {}
        tags = event.get("tags") or []
        kind = event.get("kind")
        pubkey = str(event.get("pubkey") or "")
        if COMMONS_TAG not in tags:
            return "reject", "blocked: not a Zebra Commons event"
        if kind == RECEIPT_KIND:
            if self.operator and pubkey == self.operator:
                return "accept", ""
            return "reject", "blocked: receipts come only from the relay operator"
        if kind in (DEVICE_CERT_KIND, DEVICE_REVOKE_KIND):
            if pubkey not in self.zebras:
                return "reject", "blocked: not a registered Zebra key"
            return self._identity(event, kind)
        if kind == SKILL_KIND:
            if PROTECTED_TAG not in tags:
                return "reject", "blocked: SKILL events must be protected (NIP-70)"
            if request.get("authed") != pubkey:
                return "reject", "auth-required: authenticate as the SKILL's author"
            if not self.device_ok(pubkey, int(time.time())):
                return "reject", "blocked: device has no valid cert from a registered Zebra"
            self._journal(event, pubkey, None)
            return "accept", ""
        return "reject", "blocked: kind not accepted on this relay"

    def _identity(self, event: dict, kind: int) -> tuple[str, str]:
        tags = event.get("tags") or []
        if kind == DEVICE_CERT_KIND:
            d_values, p_values = _tag_values(tags, "d"), _tag_values(tags, "p")
            if len(d_values) != 1 or p_values != d_values or not _is_key(d_values[0]):
                return "reject", "invalid: malformed DEVICE_CERT"
            try:
                content = json.loads(event.get("content") or "")
                expires = content.get("expires_at")
            except (ValueError, AttributeError):
                return "reject", "invalid: malformed DEVICE_CERT"
            if expires is not None and (isinstance(expires, bool) or not isinstance(expires, int)):
                return "reject", "invalid: malformed DEVICE_CERT"
            self._journal(event, d_values[0], expires)
            return "accept", ""
        p_values = [p for p in _tag_values(tags, "p") if _is_key(p)]
        if len(p_values) != 1:
            return "reject", "invalid: malformed DEVICE_REVOKE"
        self._journal(event, p_values[0], None)
        return "accept", ""


def main() -> None:
    policy = Policy(
        os.environ.get("ZEBRA_SYNC_ALLOWLIST", "/etc/zebra-sync/allowlist.json"),
        os.environ.get("ZEBRA_SYNC_JOURNAL", "/receipts/journal.jsonl"),
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
