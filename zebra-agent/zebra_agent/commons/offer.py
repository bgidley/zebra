"""``OFFER`` events: a workflow published to the public Commons (#231, S4).

An ``OFFER`` is an addressable Nostr event (kind ``OFFER_KIND``, ``d`` = the workflow's
content hash) signed by a certified device key and attributed to its Zebra through the
device's ``DEVICE_CERT``. Content (canonical JSON)::

    {name, summary, use_when, stats: {runs, success_rate, avg_rating, gym_score},
     actions: [...], golden_tasks: [{goal, expected, criteria}] (1-3), yaml}

Tags: ``d`` and ``x`` = sha256 of ``yaml`` (``provenance.content_sha256``), ``zebra`` = the
publisher Zebra's pubkey, ``t`` = ``zebra-commons``, ``v`` = ``1`` and, only when that parent
was itself publicly offered by this Zebra, ``parent`` = the parent's hash. A private ancestor
is never referenced, not even by hash (``public_parent``).

``offer_refusal`` holds the preconditions every offer must meet; the *Commons Offer*
workflow checks them when it starts and again just before publishing.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from zebra_agent.commons import commons_exportable, keys
from zebra_agent.commons.events import COMMONS_TAG, PROTOCOL_VERSION_TAG, Event, sign_event
from zebra_agent.commons.identity import ChainResult, verify_attributed, verify_device_chain
from zebra_agent.commons.kinds import OFFER_KIND
from zebra_agent.provenance import NotHashableError, content_sha256

if TYPE_CHECKING:
    from zebra_agent.library import WorkflowInfo, WorkflowLibrary
    from zebra_agent.metrics import WorkflowStats

#: Runs of a workflow on this deployment before it may be offered (design § Configuration).
MIN_RUNS_TO_OFFER = 5
MAX_GOLDEN_TASKS = 3
#: The ``share_with`` entry that lets a workflow go to the public Commons.
PUBLIC_SPHERE = "public"
CONTENT_KEYS = frozenset(
    {"name", "summary", "use_when", "stats", "actions", "golden_tasks", "yaml"}
)
STATS_KEYS = ("runs", "success_rate", "avg_rating", "gym_score")
MAX_TEXT = 2000


class OfferRefused(ValueError):
    """An offer cannot be built or published; the message says why."""


@dataclass
class OfferVerification:
    """The outcome of ``verify_offer``; ``reason`` is ``ok`` when accepted."""

    ok: bool
    reason: str
    zebra_pubkey: str | None = None
    content_sha256: str | None = None
    parent: str | None = None
    content: dict[str, Any] = field(default_factory=dict)


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    return " ".join(str(value or "").split())[:limit]


def golden_payload(task: Mapping[str, Any]) -> dict[str, Any]:
    """The shareable part of a golden task: ``{goal, expected, criteria}`` (strings)."""
    criteria = task.get("criteria") or []
    if isinstance(criteria, str):
        criteria = [criteria]
    return {
        "goal": _text(task.get("goal")),
        "expected": _text(task.get("expected")),
        "criteria": [_text(c, 500) for c in criteria if _text(c, 500)][:10],
    }


def offer_stats(stats: WorkflowStats | None, gym_score: float | None) -> dict[str, Any]:
    """``{runs, success_rate, avg_rating, gym_score}`` from the metrics store (numbers only)."""
    runs = int(stats.total_runs) if stats else 0
    rating = stats.avg_rating if stats else None
    return {
        "runs": runs,
        "success_rate": round(float(stats.success_rate), 3) if stats and runs else 0.0,
        "avg_rating": round(float(rating), 2) if rating is not None else None,
        "gym_score": round(float(gym_score), 3) if gym_score is not None else None,
    }


def offer_content(
    *,
    name: str,
    summary: str,
    use_when: str,
    stats: Mapping[str, Any],
    actions: list[str],
    golden_tasks: list[Mapping[str, Any]],
    yaml: str,
) -> dict[str, Any]:
    """Validated ``OFFER`` content.

    Raises:
        OfferRefused: Empty summary, no or more than ``MAX_GOLDEN_TASKS`` golden tasks, a
            golden task without a goal or criteria, or bad stats.
    """
    golden = [golden_payload(t) for t in golden_tasks or []]
    if not 1 <= len(golden) <= MAX_GOLDEN_TASKS:
        raise OfferRefused(f"an offer needs 1-{MAX_GOLDEN_TASKS} golden tasks, got {len(golden)}")
    if any(not g["goal"] or not g["criteria"] for g in golden):
        raise OfferRefused("every golden task needs a goal and pass criteria")
    if not _text(summary):
        raise OfferRefused("an offer needs a summary")
    if set(stats) != set(STATS_KEYS):
        raise OfferRefused(f"stats must be exactly {', '.join(STATS_KEYS)}")
    return {
        "name": _text(name, 200),
        "summary": _text(summary),
        "use_when": _text(use_when),
        "stats": {k: stats[k] for k in STATS_KEYS},
        "actions": sorted({str(a) for a in actions or [] if a}),
        "golden_tasks": golden,
        "yaml": yaml,
    }


def public_parent(block: Mapping[str, Any] | None, offered: Collection[str]) -> str | None:
    """The ``parent`` tag value: the block's ``parent_sha256`` only if it was publicly offered.

    *offered* is every content hash this Zebra has published an ``OFFER`` of. Otherwise
    None: the public tree starts at the first public version (design § Genealogy view).
    """
    parent = (block or {}).get("parent_sha256")
    return parent if isinstance(parent, str) and parent in offered else None


def build_offer(
    content: Mapping[str, Any],
    *,
    device_secret: str,
    zebra_pubkey: str,
    chain: list[Event],
    parent: str | None = None,
    created_at: int | None = None,
) -> Event:
    """Sign an ``OFFER`` of *content* (from ``offer_content``) with the device key.

    Raises:
        OfferRefused: Bad content keys, YAML that does not hash, or a device not attributed
            to *zebra_pubkey* by a valid cert in *chain*.
    """
    if set(content) != CONTENT_KEYS:
        raise OfferRefused("offer content has the wrong keys")
    try:
        digest = content_sha256(content["yaml"])
    except NotHashableError as e:
        raise OfferRefused(f"workflow is not hashable: {e}") from e
    device_pubkey = keys.public_key(device_secret)
    if device_pubkey != zebra_pubkey:
        check = verify_device_chain(device_pubkey, zebra_pubkey, chain, now=created_at)
        if not check.ok:
            raise OfferRefused(f"this device is not attributed to its Zebra ({check.reason})")
    tags = [
        ["d", digest],
        ["x", digest],
        ["zebra", zebra_pubkey],
        COMMONS_TAG,
        PROTOCOL_VERSION_TAG,
    ]
    if parent:
        tags.append(["parent", parent])
    text = json.dumps(dict(content), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sign_event(device_secret, OFFER_KIND, tags, text, created_at)


def verify_offer(
    event: Event,
    chain_events: list[Event],
    *,
    expected_zebra: str | None = None,
    now: int | None = None,
    receipt_seq: Mapping[str, int] | None = None,
) -> OfferVerification:
    """Check an ``OFFER``: kind, tags, content shape, hash, and attribution to its Zebra.

    Reasons: ``ok``, ``wrong_kind``, ``malformed``, ``wrong_zebra``, ``not_hashable``,
    ``hash_mismatch`` and the attribution reasons of ``verify_attributed`` (``bad_signature``,
    ``no_cert``, ``revoked``, ``expired``, ...).
    """
    if event.kind != OFFER_KIND:
        return OfferVerification(False, "wrong_kind")
    zebras, d, x = event.tag_values("zebra"), event.tag_values("d"), event.tag_values("x")
    parents = event.tag_values("parent")
    if len(zebras) != 1 or len(d) != 1 or d != x or len(parents) > 1:
        return OfferVerification(False, "malformed")
    if COMMONS_TAG not in event.tags or PROTOCOL_VERSION_TAG not in event.tags:
        return OfferVerification(False, "malformed")
    zebra = zebras[0]
    if expected_zebra is not None and zebra != expected_zebra:
        return OfferVerification(False, "wrong_zebra", zebra_pubkey=zebra)
    content = event.json_content()
    if content is None or set(content) != CONTENT_KEYS or not isinstance(content["yaml"], str):
        return OfferVerification(False, "malformed", zebra_pubkey=zebra)
    golden = content.get("golden_tasks")
    if not isinstance(golden, list) or not 1 <= len(golden) <= MAX_GOLDEN_TASKS:
        return OfferVerification(False, "malformed", zebra_pubkey=zebra)
    try:
        digest = content_sha256(content["yaml"])
    except NotHashableError:
        return OfferVerification(False, "not_hashable", zebra_pubkey=zebra)
    if digest != d[0]:
        return OfferVerification(False, "hash_mismatch", zebra_pubkey=zebra)
    attributed: ChainResult = verify_attributed(
        event, zebra, chain_events, now=now, receipt_seq=receipt_seq
    )
    if not attributed.ok:
        return OfferVerification(False, attributed.reason, zebra_pubkey=zebra)
    return OfferVerification(
        True,
        "ok",
        zebra_pubkey=zebra,
        content_sha256=digest,
        parent=parents[0] if parents else None,
        content=content,
    )


def offer_refusal(
    info: WorkflowInfo | None,
    library: WorkflowLibrary,
    runs: int,
    *,
    min_runs: int = MIN_RUNS_TO_OFFER,
) -> str | None:
    """Why this workflow may not be offered now, or None. Fails closed.

    - not ``commons_exportable`` (protected, ``foreign_users``, or no ``commons`` block);
    - the leak guard kept run specifics in this version or an ancestor, or never checked
      them (``sync.leak_kept``);
    - fewer than *min_runs* recorded runs.

    ``public`` in ``share_with`` is checked at publish time (``publish_refusal``).
    """
    from zebra_agent.commons.sync import leak_kept

    if info is None:
        return "no active workflow by that name"
    if not commons_exportable(info):
        return (
            "this workflow may not leave this deployment (a system workflow, learnt from "
            "other users' runs, or no provenance yet)"
        )
    block = info.commons or {}
    if leak_kept(library, block.get("content_sha256"), block):
        return "the leak guard kept (or never checked) run specifics in this version or an ancestor"
    if runs < min_runs:
        return f"it has {runs} recorded run(s); an offer needs at least {min_runs}"
    return None


def publish_refusal(
    info: WorkflowInfo | None,
    library: WorkflowLibrary,
    runs: int,
    expected_sha256: str | None,
    *,
    min_runs: int = MIN_RUNS_TO_OFFER,
) -> str | None:
    """``offer_refusal`` plus what publishing needs: the approved version, ``public`` shared."""
    reason = offer_refusal(info, library, runs, min_runs=min_runs)
    if reason:
        return reason
    block = (info.commons if info else None) or {}
    if not expected_sha256 or block.get("content_sha256") != expected_sha256:
        return "the workflow changed since the offer was prepared"
    if PUBLIC_SPHERE not in (block.get("share_with") or []):
        return "'public' is not in this version's share_with (no current approval)"
    return None
