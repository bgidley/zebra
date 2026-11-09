"""The web of trust: ``TRUST`` events, local trust and the import score (#233, S6).

A ``TRUST`` event says "Zebra *from* trusts Zebra *to* this much"::

    kind    30233 (addressable, one current event per signer and target)
    tags    ["d",<target>], ["p",<target>], ["zebra",<trusting Zebra>], ["t","zebra-commons"],
            ["v","1"]
    content {"reason": <fixed word or the owner's note>, "weight": -1..1 (2 places)}

It is signed by a certified device key and attributed to its Zebra through the device's
``DEVICE_CERT``, like ``ATTEST``: devices do not hold the Zebra key.

Trust is only ever set by the owner (vouch, withdraw, distrust) or by this Zebra's own
attestations (an EWMA, ``experience_update``). No LLM sets trust. Local trust is computed here,
deterministically, from the edges held (``compute_trust``); nothing global exists.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from zebra_agent.commons import keys
from zebra_agent.commons.attest import (
    FAILED,
    PII_FOUND,
    REJECTED_ETHICS,
    REJECTED_GYM,
    WORKED,
)
from zebra_agent.commons.events import COMMONS_TAG, PROTOCOL_VERSION_TAG, Event, sign_event
from zebra_agent.commons.identity import verify_attributed, verify_device_chain
from zebra_agent.commons.kinds import TRUST_KIND

#: The weight of the owner's "I know this Zebra".
VOUCH_WEIGHT = 0.8
#: The weight of the owner's "I do not trust this Zebra".
DISTRUST_WEIGHT = -0.8
#: Decay per hop beyond the first: ``∏ weights × DECAY^(hops-1)``.
DECAY = 0.9
#: The longest trust path, in hops (edges).
MAX_HOPS = 3
#: EWMA learning rate of experience.
EXPERIENCE_RATE = 0.2
#: An experience change is published only when it moved this far from the last published weight.
PUBLISH_THRESHOLD = 0.1
#: Import score weights: local trust of the publisher, market (parked: 0), attestations.
ALPHA = 0.7
BETA = 0.0
GAMMA = 0.3
#: Offers below this score are never judged automatically (S8); the owner is warned.
IMPORT_SCORE_THRESHOLD = 0.5

VOUCHED = "vouched"
WITHDRAWN = "withdrawn"
DISTRUSTED = "distrusted"
EXPERIENCE = "experience"
#: The fixed reasons; anything else is the owner's own note.
REASONS = (VOUCHED, WITHDRAWN, DISTRUSTED, EXPERIENCE)
MAX_NOTE = 140

#: What one of this Zebra's own attestations says about the publisher (+1 / -1).
#: ``adopted`` and ``rejected-pii`` (the scan failed closed) say nothing about it.
EXPERIENCE_SIGNAL: dict[str, float] = {
    WORKED: 1.0,
    FAILED: -1.0,
    REJECTED_ETHICS: -1.0,
    REJECTED_GYM: -1.0,
    PII_FOUND: -1.0,
}

_KEY = re.compile(r"^[0-9a-f]{64}$")
_TAG_NAMES = ("d", "p", "zebra", "t", "v")


class TrustRefused(ValueError):
    """A ``TRUST`` event cannot be built; the message says why."""


@dataclass(frozen=True)
class TrustVerification:
    """The outcome of ``verify_trust``; ``reason`` is ``ok`` when accepted."""

    ok: bool
    reason: str
    from_pubkey: str | None = None
    to_pubkey: str | None = None
    weight: float | None = None
    trust_reason: str | None = None


def clean_reason(reason: str | None) -> str:
    """A fixed reason, or the owner's note (1-140 printable characters, one line).

    Raises:
        TrustRefused: Empty, too long, or with control characters.
    """
    if reason in REASONS:
        return reason
    text = (reason or "").strip()
    if not text:
        raise TrustRefused("a trust reason is required")
    if len(text) > MAX_NOTE:
        raise TrustRefused(f"a trust note is at most {MAX_NOTE} characters")
    if any(not ch.isprintable() for ch in text):
        raise TrustRefused("a trust note is one line of plain text")
    return text


def canonical_weight(weight: float) -> float:
    """*weight* rounded to 2 places. Raises ``TrustRefused`` outside -1..1 or not a number."""
    if isinstance(weight, bool) or not isinstance(weight, int | float) or math.isnan(weight):
        raise TrustRefused("a trust weight is a number")
    if not -1.0 <= float(weight) <= 1.0:
        raise TrustRefused("a trust weight is between -1 and 1")
    value = round(float(weight), 2)
    return 0.0 if value == 0 else value


def trust_content(weight: float, reason: str) -> str:
    """The canonical content JSON (sorted keys, weight to 2 places)."""
    body = {"reason": clean_reason(reason), "weight": canonical_weight(weight)}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def trust_tags(target: str, zebra_pubkey: str) -> list[list[str]]:
    """The fixed tag set of a ``TRUST`` event."""
    return [
        ["d", target],
        ["p", target],
        ["zebra", zebra_pubkey],
        COMMONS_TAG,
        PROTOCOL_VERSION_TAG,
    ]


def build_trust(
    target: str,
    weight: float,
    reason: str,
    *,
    device_secret: str,
    zebra_pubkey: str,
    chain: list[Event],
    created_at: int | None = None,
) -> Event:
    """Sign a ``TRUST`` of *weight* in *target* with the device key.

    Raises:
        TrustRefused: A bad target, weight or reason, trusting oneself, or a device that is not
            attributed to *zebra_pubkey* by a valid cert in *chain*.
    """
    if not isinstance(target, str) or not _KEY.match(target):
        raise TrustRefused("the trusted Zebra must be a 64-character hex public key")
    if target == zebra_pubkey:
        raise TrustRefused("a Zebra cannot trust itself")
    content = trust_content(weight, reason)
    device_pubkey = keys.public_key(device_secret)
    if device_pubkey != zebra_pubkey:
        check = verify_device_chain(device_pubkey, zebra_pubkey, chain, now=created_at)
        if not check.ok:
            raise TrustRefused(f"this device is not attributed to its Zebra ({check.reason})")
    return sign_event(
        device_secret, TRUST_KIND, trust_tags(target, zebra_pubkey), content, created_at
    )


def verify_trust(
    event: Event,
    chain_events: list[Event],
    *,
    now: int | None = None,
    receipt_seq: Mapping[str, int] | None = None,
) -> TrustVerification:
    """Check a ``TRUST``: kind, exact tags, canonical content, attribution.

    Reasons: ``ok``, ``wrong_kind``, ``malformed``, ``bad_weight``, ``bad_reason``, ``self`` and
    the attribution reasons of ``verify_attributed`` (``bad_signature``, ``no_cert``, ...).
    """
    if event.kind != TRUST_KIND:
        return TrustVerification(False, "wrong_kind")
    if len(event.tags) != len(_TAG_NAMES) or any(
        not t or t[0] not in _TAG_NAMES for t in event.tags
    ):
        return TrustVerification(False, "malformed")
    targets, zebras = event.tag_values("d"), event.tag_values("zebra")
    if len(targets) != 1 or len(zebras) != 1:
        return TrustVerification(False, "malformed")
    target, zebra = targets[0], zebras[0]
    if not _KEY.match(target) or not _KEY.match(zebra) or event.tags != trust_tags(target, zebra):
        return TrustVerification(False, "malformed", from_pubkey=zebra)
    if target == zebra:
        return TrustVerification(False, "self", from_pubkey=zebra)
    content = event.json_content()
    if content is None or set(content) != {"reason", "weight"}:
        return TrustVerification(False, "malformed", from_pubkey=zebra)
    try:
        weight = canonical_weight(content["weight"])
    except TrustRefused:
        return TrustVerification(False, "bad_weight", from_pubkey=zebra)
    try:
        canonical = trust_content(weight, content["reason"])
    except TrustRefused:
        return TrustVerification(False, "bad_reason", from_pubkey=zebra)
    if canonical != event.content:
        return TrustVerification(False, "malformed", from_pubkey=zebra)
    attributed = verify_attributed(event, zebra, chain_events, now=now, receipt_seq=receipt_seq)
    if not attributed.ok:
        return TrustVerification(False, attributed.reason, from_pubkey=zebra)
    return TrustVerification(
        True,
        "ok",
        from_pubkey=zebra,
        to_pubkey=target,
        weight=weight,
        trust_reason=content["reason"],
    )


# -- experience ------------------------------------------------------------------------------


def experience_update(
    current: float | None, label: str, *, owner_weight: float | None = None
) -> float | None:
    """The edge after one of this Zebra's own attestations *label*, or None if it says nothing.

    ``w' = (1 - EXPERIENCE_RATE)·w + EXPERIENCE_RATE·signal`` from *current* (0 when no edge).
    The owner's weight bounds it: a vouch is a floor, a distrust a ceiling.
    """
    signal = EXPERIENCE_SIGNAL.get(label)
    if signal is None:
        return None
    value = (1 - EXPERIENCE_RATE) * (current or 0.0) + EXPERIENCE_RATE * signal
    if owner_weight is not None and owner_weight > 0:
        value = max(value, owner_weight)
    elif owner_weight is not None and owner_weight < 0:
        value = min(value, owner_weight)
    return max(-1.0, min(1.0, value))


def should_publish(weight: float, published: float | None) -> bool:
    """Whether an experience change is big enough to publish (never published: yes)."""
    if published is None:
        return True
    return abs(round(weight, 2) - published) >= PUBLISH_THRESHOLD - 1e-9


# -- local trust -----------------------------------------------------------------------------


@dataclass(frozen=True)
class TrustPath:
    """The best path to a Zebra: ``hops`` are ``(from, to, weight)``; value 0 means no path."""

    value: float
    hops: tuple[tuple[str, str, float], ...] = field(default_factory=tuple)

    @property
    def nodes(self) -> list[str]:
        return [self.hops[0][0], *(h[1] for h in self.hops)] if self.hops else []

    def to_dict(self) -> dict:
        return {"value": self.value, "hops": [list(h) for h in self.hops]}

    @classmethod
    def from_dict(cls, data: Mapping | None) -> TrustPath:
        data = data or {}
        hops = tuple((str(a), str(b), float(w)) for a, b, w in data.get("hops") or [])
        return cls(float(data.get("value") or 0.0), hops)


NO_PATH = TrustPath(0.0)


def path_value(weights: Iterable[float]) -> float:
    """``∏ weights × DECAY^(hops-1)``."""
    weights = list(weights)
    if not weights:
        return 0.0
    return math.prod(weights) * DECAY ** (len(weights) - 1)


def _better(a: tuple[float, int, tuple[str, ...]], b: tuple[float, int, tuple[str, ...]]) -> bool:
    """Higher value; then fewer hops; then the smaller path (deterministic)."""
    va, vb = round(a[0], 9), round(b[0], 9)
    if va != vb:
        return va > vb
    if a[1] != b[1]:
        return a[1] < b[1]
    return a[2] < b[2]


def compute_trust(
    me: str, edges: Mapping[tuple[str, str], float], seeds: Iterable[str]
) -> dict[str, TrustPath]:
    """Local trust of every Zebra this Zebra can see, from *edges* ``{(from, to): weight}``.

    - A path has 1 to ``MAX_HOPS`` edges, starts at *me* and its first edge goes to a
      human-vouched seed (Sybil limit: nothing else starts a path).
    - Interior edges must be positive; a negative edge is only ever the last hop.
    - Value ``∏ weights × DECAY^(hops-1)``; trust is the max over paths.
    - Zebras a path reaches are *anchored*; *me*'s own direct edge to an anchored Zebra is a
      candidate too. *me*'s own negative edge always wins, and a Zebra *me* distrusts is never
      a hop of any path: whoever it vouches for gains nothing from it.
    - Zero edges are no edges. Deterministic: ties go to fewer hops, then the smaller path.

    Returns ``{pubkey: TrustPath}`` for every Zebra with a path (others have trust 0).
    """
    seeds = set(seeds) - {me}
    out_edges: dict[str, list[tuple[str, float]]] = {}
    for (a, b), w in sorted(edges.items()):
        if w and a != b:
            out_edges.setdefault(a, []).append((b, float(w)))
    distrusted = {b for b, w in out_edges.get(me, []) if w < 0}
    best: dict[str, tuple[float, int, tuple[str, ...], tuple[tuple[str, str, float], ...]]] = {}

    def offer(target: str, hops: tuple[tuple[str, str, float], ...]) -> None:
        value = path_value(h[2] for h in hops)
        key = (value, len(hops), tuple(h[1] for h in hops))
        current = best.get(target)
        if current is None or _better(key, current[:3]):
            best[target] = (*key, hops)

    def walk(node: str, hops: tuple[tuple[str, str, float], ...], visited: frozenset[str]) -> None:
        if len(hops) >= MAX_HOPS:
            return
        for nxt, w in out_edges.get(node, []):
            if nxt in visited or nxt == me or nxt in distrusted:
                continue
            path = (*hops, (node, nxt, w))
            offer(nxt, path)
            if w > 0:
                walk(nxt, path, visited | {nxt})

    for seed, w in out_edges.get(me, []):
        if seed in seeds and w > 0 and seed not in distrusted:
            first = ((me, seed, w),)
            offer(seed, first)
            walk(seed, first, frozenset({me, seed}))

    anchored = {t for t, v in best.items() if v[0] > 0} | seeds
    for target, w in out_edges.get(me, []):
        if w < 0:
            best[target] = (w, 1, (target,), ((me, target, w),))
        elif target in anchored:
            offer(target, ((me, target, w),))
    return {t: TrustPath(round(v[0], 6), v[3]) for t, v in sorted(best.items())}


def path_text(path: TrustPath, name) -> str:
    """``B via A: 0.8 × 0.6 × 0.9 = 0.43`` (*name* maps a pubkey to a label)."""
    if not path.hops:
        return "no path from a Zebra you know"
    target = name(path.hops[-1][1])
    weights = " × ".join(f"{h[2]:g}" for h in path.hops)
    if len(path.hops) > 1:
        weights += f" × {DECAY:g}" + (f"^{len(path.hops) - 1}" if len(path.hops) > 2 else "")
    via = [name(h[1]) for h in path.hops[:-1]]
    head = f"{target} via {' → '.join(via)}" if via else f"{target} directly"
    return f"{head}: {weights} = {path.value:.2f}"


# -- import score ----------------------------------------------------------------------------


def attestation_signal(
    reports: Iterable[tuple[str, str]],
    trust: Mapping[str, float],
    *,
    exclude: Iterable[str] = (),
) -> float:
    """Trust-weighted mean of ``worked`` (+1) and ``failed`` (-1) over ``(zebra, label)`` reports.

    Only reporters with positive local trust count; *exclude* (this Zebra, the publisher) never
    does. 0 when no trusted Zebra reported.
    """
    skip = set(exclude)
    total = weight_sum = 0.0
    for zebra, label in reports:
        value = {WORKED: 1.0, FAILED: -1.0}.get(label)
        t = trust.get(zebra, 0.0)
        if value is None or zebra in skip or t <= 0:
            continue
        total += t * value
        weight_sum += t
    return total / weight_sum if weight_sum else 0.0


def import_score(local_trust: float, signal: float, market: float = 0.0) -> float:
    """``α·local_trust + β·market + γ·attestation_signal`` (β = 0 while the market is parked)."""
    return round(ALPHA * local_trust + BETA * market + GAMMA * signal, 4)


def clears_threshold(score: float) -> bool:
    """Whether an offer with *score* may be judged automatically (S8)."""
    return score >= IMPORT_SCORE_THRESHOLD
