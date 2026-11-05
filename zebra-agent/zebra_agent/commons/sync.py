"""Skill sync between one Zebra's own devices (#236, S3b-1).

A workflow learnt in one sphere (home, work) stays there until Zebra suggests sharing it and
the share is approved; then it travels as ``SKILL`` events to the certified devices of the
approved sphere only. Data never travels. See ``specs/zebra-commons-design.md`` § "Skill sync
between own devices (S3b)".

- ``SyncService`` is this device's sync identity and transport, injected into the engine as
  ``extras["__commons_sync__"]``. It finds share candidates, starts the *Skill Share* and
  *Skill Receive* system workflows, sends approved workflows and merges received ones.
- Share decisions are records in the lineage journal (#238), keyed on (content hash,
  sphere), so Zebra asks once per version and the genealogy shows each sphere's status.
- ``merge_decision`` places a received version by ``commons.ancestors``.

The transport here is any ``CommonsClient``; until #246 only ``InMemoryCommonsClient``.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from zebra_agent.commons import commons_exportable, keys
from zebra_agent.commons.client import SKILL_KIND, CommonsClient, Filter
from zebra_agent.commons.events import Event
from zebra_agent.commons.identity import (
    DEVICE_CERT_KIND,
    DEVICE_REVOKE_KIND,
    DeviceCert,
    parse_cert,
    verify_device_chain,
)
from zebra_agent.commons.skill import (
    SkillRefused,
    SkillVerification,
    build_skill_events,
    skill_payload,
    skill_recipients,
    verify_skill,
)
from zebra_agent.genealogy import _RETIRED_MARKER as RETIRED_MARKER
from zebra_agent.provenance import read_commons, strip_commons, try_content_sha256

if TYPE_CHECKING:
    from zebra.core.engine import WorkflowEngine

    from zebra_agent.library import WorkflowLibrary
    from zebra_agent.metrics import MetricsStore

logger = logging.getLogger(__name__)

SYNC_DIRECTIONS = ("send", "receive", "both", "off")
MIN_RUNS_TO_SHARE = 2
SKILL_SHARE_WORKFLOW = "Skill Share"
SKILL_RECEIVE_WORKFLOW = "Skill Receive"

SHARE_EVENT = "share"
PROPOSED = "proposed"
APPROVED = "approved"
DECLINED = "declined"
SENSITIVE = "sensitive"  # never proposed to that (observed) sphere
BLOCKED = "blocked"  # a scan or the leak guard stopped it
SENT = "sent"
RECEIVED = "received"
REJECTED = "rejected"  # a received event that failed the receive pipeline
# Statuses after which Zebra does not propose the same version to the same sphere again.
DECIDED = frozenset({PROPOSED, APPROVED, DECLINED, SENSITIVE, BLOCKED, SENT, RECEIVED})
STATUS_LABELS = {
    PROPOSED: "waiting for approval",
    APPROVED: "approved",
    DECLINED: "declined",
    SENSITIVE: "never proposed (sensitive)",
    BLOCKED: "blocked",
    SENT: "shared",
    RECEIVED: "received from there",
    REJECTED: "rejected on arrival",
}

NEW, NOOP, FAST_FORWARD, STALE, FORK = "new", "noop", "fast_forward", "stale", "fork"


def can_send(direction: str | None) -> bool:
    """Whether a device with this ``sync_direction`` may send (unknown: no)."""
    return direction in ("send", "both")


def can_receive(direction: str | None) -> bool:
    """Whether a device with this ``sync_direction`` may receive (unknown: no)."""
    return direction in ("receive", "both")


def bytes_sha256(text: str) -> str:
    """sha256 of the exact UTF-8 bytes of *text* (what the scans saw is what is sent)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def merge_decision(local: dict[str, Any] | None, incoming: dict[str, Any]) -> str:
    """Place a received version against the local one, like git (design § S3b step 3).

    ``new`` (nothing local), ``noop`` (same hash), ``fast_forward`` (the local hash is in
    the incoming ancestors), ``stale`` (the incoming hash is in the local ancestors) or
    ``fork`` (neither, including a lineage longer than ``ANCESTOR_WINDOW``).
    """
    incoming_hash = incoming.get("content_sha256")
    if not local:
        return NEW
    local_hash = local.get("content_sha256")
    if local_hash == incoming_hash:
        return NOOP
    if local_hash and local_hash in _lineage(incoming):
        return FAST_FORWARD
    if incoming_hash and incoming_hash in _lineage(local):
        return STALE
    return FORK


def _lineage(block: dict[str, Any]) -> set[str]:
    out = {a for a in block.get("ancestors") or [] if isinstance(a, str)}
    if isinstance(block.get("parent_sha256"), str):
        out.add(block["parent_sha256"])
    return out


# --- share decisions in the lineage journal -------------------------------------------


def record_share(
    library: WorkflowLibrary,
    name: str,
    content_hash: str | None,
    sphere: str,
    status: str,
    *,
    reason: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Append one share decision to the library's lineage journal and return it."""
    record = {
        "v": 1,
        "at": datetime.now(UTC).isoformat(timespec="microseconds"),
        "event": SHARE_EVENT,
        "name": name,
        "content_sha256": content_hash,
        "sphere": sphere,
        "status": status,
        "from_sphere": library.sphere,
        "reason": (reason or "")[:500] or None,
        "event_id": event_id,
    }
    library.journal.append(record)
    logger.info("Share %r (%s) with %s: %s", name, (content_hash or "-")[:12], sphere, status)
    return record


def share_records(library: WorkflowLibrary) -> list[dict[str, Any]]:
    """Every share record, oldest first."""
    return [r for r in library.journal.read() if r.get("event") == SHARE_EVENT]


def latest_decision(library: WorkflowLibrary, content_hash: str, sphere: str) -> str | None:
    """The newest share status for (*content_hash*, *sphere*), or None."""
    status = None
    for r in share_records(library):
        if r.get("content_sha256") == content_hash and r.get("sphere") == sphere:
            status = r.get("status")
    return status


#: Leak-guard results that taint a version and every descendant (#237: ``kept`` = tainted;
#: ``error`` = never checked, so fail closed).
LEAK_TAINTED = frozenset({"kept", "error"})


def _leak_tainted_record(leak: dict[str, Any] | None) -> bool:
    if not isinstance(leak, dict):
        return False
    return bool(
        leak.get("status") in LEAK_TAINTED
        or leak.get("save_check") in LEAK_TAINTED
        or leak.get("check_failed")
    )


def leak_kept(
    library: WorkflowLibrary, content_hash: str | None, block: dict[str, Any] | None = None
) -> bool:
    """Whether this version, or any version it descends from, carries leak-guard taint.

    A journal ``saved`` record taints its hash when the writer's status or the save-time
    check (``save_check``) is ``kept`` or ``error``, or the check failed. The taint passes to
    every descendant: the leak guard never flags a literal already in the parent, so an edit
    of a ``kept`` version still carries it. *block* gives the version's lineage
    (``ancestors``, ``parent_sha256``). A version with no hash is treated as tainted.
    """
    if not content_hash:
        return True
    lineage = {content_hash} | _lineage(block or {})
    for r in library.journal.read():
        if r.get("event") != "saved" or r.get("content_sha256") not in lineage:
            continue
        if _leak_tainted_record(r.get("leak_guard")):
            return True
    return False


def share_status(
    library: WorkflowLibrary, name: str, content_hash: str | None, block: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Per-sphere status of the current version, for the genealogy page (#238).

    ``shared`` for every sphere in ``share_with``; otherwise the newest journal decision
    for this hash and sphere. Spheres never considered are not listed.
    """
    statuses: dict[str, dict[str, Any]] = {}
    for r in share_records(library):
        if r.get("content_sha256") != content_hash or not r.get("sphere"):
            continue
        statuses[r["sphere"]] = {"sphere": r["sphere"], "status": r.get("status"), "at": r["at"]}
    for sphere in (block or {}).get("share_with") or []:
        if not isinstance(sphere, str):
            continue
        current = statuses.get(sphere, {})
        if current.get("status") not in (SENT, RECEIVED):
            statuses[sphere] = {"sphere": sphere, "status": APPROVED, "at": current.get("at")}
    for entry in statuses.values():
        entry["label"] = STATUS_LABELS.get(entry["status"], entry["status"])
    return sorted(statuses.values(), key=lambda e: e["sphere"])


def version_yaml(library: WorkflowLibrary, content_hash: str) -> str | None:
    """The YAML (no block) of any file on this device, active or retired, with this hash."""
    for directory in (library.library_path, library.retired_path):
        if not directory.is_dir():
            continue
        for path in directory.glob("*.yaml"):
            try:
                text = path.read_text().split(RETIRED_MARKER, 1)[0]
            except OSError:
                continue
            block = read_commons(text) or {}
            found = block.get("content_sha256") or try_content_sha256(text)[0]
            if found == content_hash:
                return strip_commons(text)
    return None


def diff_text(old: str | None, new: str, old_label: str, new_label: str) -> str:
    """A unified diff, or a note when there is no earlier copy."""
    if old is None:
        return f"(no copy in {old_label} yet: the whole workflow is new there)"
    lines = difflib.unified_diff(
        old.splitlines(), new.splitlines(), fromfile=old_label, tofile=new_label, lineterm=""
    )
    return "\n".join(list(lines)[:400]) or "(no changes)"


# --- the service ----------------------------------------------------------------------


@dataclass
class SyncService:
    """This device's skill sync: identity, direction, transport (``__commons_sync__``).

    Attributes:
        client: The private sync relay (``CommonsClient``)
        device_secret: This device's secret key (never logged)
        zebra_pubkey: This device's Zebra key
        sphere: This device's sphere; ``observed`` whether it is managed by someone else
        direction: ``send`` / ``receive`` / ``both`` / ``off``
        certs: The ``DEVICE_CERT`` / ``DEVICE_REVOKE`` events of this Zebra held here
        confidential_patterns: ``SYNC_CONFIDENTIAL_PATTERNS`` of this device
        device_label: This device's label
        min_runs: Successful runs before Zebra suggests sharing (``MIN_RUNS_TO_SHARE``)
    """

    client: CommonsClient
    device_secret: str = field(repr=False)
    zebra_pubkey: str
    sphere: str
    observed: bool = False
    direction: str = "both"
    certs: list[Event] = field(default_factory=list)
    confidential_patterns: list[str] = field(default_factory=list)
    device_label: str = ""
    min_runs: int = MIN_RUNS_TO_SHARE
    _started_events: set[str] = field(default_factory=set, repr=False)

    @property
    def device_pubkey(self) -> str:
        return keys.public_key(self.device_secret)

    @property
    def can_send(self) -> bool:
        return can_send(self.direction)

    @property
    def can_receive(self) -> bool:
        return can_receive(self.direction)

    def devices(self, now: int | None = None) -> list[DeviceCert]:
        """This Zebra's devices whose chain verifies now (unexpired, unrevoked)."""
        found: dict[str, DeviceCert] = {}
        for event in self.certs:
            if event.kind != DEVICE_CERT_KIND:
                continue
            cert = parse_cert(event)
            if cert is None or cert.zebra_pubkey != self.zebra_pubkey:
                continue
            check = verify_device_chain(cert.device_pubkey, self.zebra_pubkey, self.certs, now=now)
            if check.ok and check.cert is not None:
                found[cert.device_pubkey] = check.cert
        return list(found.values())

    def own_cert(self) -> Event | None:
        """This device's current ``DEVICE_CERT`` (None if uncertified or revoked)."""
        mine = self.device_pubkey
        check = verify_device_chain(mine, self.zebra_pubkey, self.certs)
        return check.cert.event if check.ok and check.cert is not None else None

    def spheres(self) -> dict[str, bool]:
        """Every sphere of this Zebra's devices → observed (any observed device counts)."""
        out: dict[str, bool] = {self.sphere: self.observed}
        for cert in self.devices():
            out[cert.sphere] = out.get(cert.sphere, False) or cert.observed
        return out

    def other_spheres(self) -> dict[str, bool]:
        """The spheres a workflow here could be shared with."""
        return {s: o for s, o in self.spheres().items() if s != self.sphere}

    def is_observed(self, sphere: str) -> bool:
        """Whether *sphere* is observed; an unknown sphere counts as observed (fail closed)."""
        return self.spheres().get(sphere, True)

    def held_events(self) -> list[Event]:
        return [e for e in self.certs if e.kind in (DEVICE_CERT_KIND, DEVICE_REVOKE_KIND)]

    # -- proposing ---------------------------------------------------------------------

    async def candidates(
        self,
        library: WorkflowLibrary,
        metrics: MetricsStore | None,
        names: list[str] | None = None,
    ) -> list[tuple[str, str]]:
        """``(workflow, sphere)`` pairs Zebra should suggest sharing now.

        Each workflow must be ``commons_exportable`` (never system, ``foreign_users`` or
        blockless), have ``min_runs`` successful runs, and not be shared with or already
        decided for that sphere at its current hash. Nothing while this device may not send
        or without metrics (fail closed).
        """
        if not self.can_send or metrics is None:
            return []
        targets = self.other_spheres()
        if not targets:
            return []
        if names is None:
            names = [w.name for w in await library.list_workflows()]
        out = []
        for name in dict.fromkeys(names):  # several files can share a name
            info = await library.get_workflow_info(name)
            if info is None or not commons_exportable(info):
                continue
            block = info.commons or {}
            content_hash = block.get("content_sha256")
            if not content_hash:
                continue
            try:
                stats = await metrics.get_stats(name)
            except Exception as e:  # noqa: BLE001 - no stats, no proposal
                logger.warning("Skill sync: no stats for %r: %s", name, e)
                continue
            if stats.successful_runs < self.min_runs:
                continue
            shared = block.get("share_with") or []
            for sphere in sorted(targets):
                if sphere in shared:
                    continue
                if latest_decision(library, content_hash, sphere) in DECIDED:
                    continue
                out.append((name, sphere))
        return out

    async def start_share(
        self,
        engine: WorkflowEngine,
        library: WorkflowLibrary,
        name: str,
        sphere: str,
        *,
        trigger: str = "runs",
        manual: bool = False,
    ) -> str | None:
        """Start a *Skill Share* process for (*name*, *sphere*); returns its id.

        ``manual`` is a human's share from the workflow page: it may reach an observed
        sphere even when sensitive, after the managed-device confirmation.
        """
        info = await library.get_workflow_info(name)
        content_hash = ((info.commons or {}) if info else {}).get("content_sha256")
        owner = await library.refresh_owner()
        properties: dict[str, Any] = {
            "workflow_name": name,
            "target_sphere": sphere,
            "trigger": "manual" if manual else trigger,
            "manual": manual,
        }
        if owner is not None:
            properties["__user_id__"] = owner
        record_share(library, name, content_hash, sphere, PROPOSED, reason=trigger)
        definition = library.get_workflow(SKILL_SHARE_WORKFLOW)
        process = await engine.create_process(definition, properties=properties)
        await engine.start_process(process.id)
        return process.id

    async def propose(
        self,
        engine: WorkflowEngine,
        library: WorkflowLibrary,
        metrics: MetricsStore | None,
        *,
        names: list[str] | None = None,
        trigger: str = "runs",
    ) -> list[str]:
        """Start a *Skill Share* for every candidate; returns the process ids."""
        started = []
        for name, sphere in await self.candidates(library, metrics, names):
            try:
                pid = await self.start_share(engine, library, name, sphere, trigger=trigger)
            except Exception as e:  # noqa: BLE001 - one failed proposal never stops the rest
                logger.warning("Skill sync: could not propose %r to %s: %s", name, sphere, e)
                continue
            if pid:
                started.append(pid)
        return started

    async def after_run(
        self,
        engine: WorkflowEngine,
        library: WorkflowLibrary,
        metrics: MetricsStore | None,
        name: str,
    ) -> list[str]:
        """Consider sharing *name* after a run (proposed once it has ``min_runs`` successes)."""
        return await self.propose(engine, library, metrics, names=[name], trigger="runs")

    async def after_dream(
        self, engine: WorkflowEngine, library: WorkflowLibrary, metrics: MetricsStore | None
    ) -> list[str]:
        """Consider every workflow after the dream cycle (rewritten ones have a new hash)."""
        return await self.propose(engine, library, metrics, trigger="dream")

    # -- sending -----------------------------------------------------------------------

    async def send(
        self,
        library: WorkflowLibrary,
        name: str,
        *,
        spheres: list[str],
        expected_sha256: str,
        scanned_bytes_sha256: str,
        stats: dict[str, Any] | None = None,
    ) -> list[Event]:
        """Send the current version of *name* to the devices of *spheres*.

        Only while this device may send, the current hash is *expected_sha256* (the approved
        version), the exact payload bytes are the ones scanned (*scanned_bytes_sha256*) and
        each sphere is in ``share_with``.

        Raises:
            SkillRefused: Any of those fails, or this device is not certified.
        """
        if not self.can_send:
            raise SkillRefused(f"sync direction {self.direction!r} does not allow sending")
        path = next(iter(library._files_named(name)), None)
        if path is None:
            raise SkillRefused(f"no active workflow named {name!r}")
        text = path.read_text()
        block = read_commons(text) or {}
        if block.get("content_sha256") != expected_sha256:
            raise SkillRefused("the workflow changed since the share was approved")
        if bytes_sha256(skill_payload(text)) != scanned_bytes_sha256:
            raise SkillRefused("the bytes to send are not the bytes that were scanned")
        if leak_kept(library, expected_sha256, block):
            raise SkillRefused("the leak guard kept run specifics in this version or an ancestor")
        own = self.own_cert()
        if own is None:
            raise SkillRefused("this device has no valid DEVICE_CERT")
        wanted = [s for s in spheres if s in (block.get("share_with") or [])]
        recipients = skill_recipients(
            wanted,
            self.devices(),
            self.held_events(),
            zebra_pubkey=self.zebra_pubkey,
            sender_pubkey=self.device_pubkey,
        )
        events = build_skill_events(
            text,
            device_secret=self.device_secret,
            zebra_pubkey=self.zebra_pubkey,
            own_cert=own,
            recipients=recipients,
            stats=stats,
            sending_device={"label": self.device_label, "sphere": self.sphere},
        )
        for event in events:
            await self.client.publish(event)
        for sphere in wanted:
            record_share(library, name, expected_sha256, sphere, SENT)
        return events

    # -- receiving ---------------------------------------------------------------------

    async def pending_events(self, library: WorkflowLibrary) -> list[Event]:
        """``SKILL`` events addressed to this device not yet handled (none if receive is off)."""
        if not self.can_receive:
            return []
        handled = {r.get("event_id") for r in share_records(library) if r.get("event_id")}
        events = await self.client.fetch(
            [Filter(kinds=(SKILL_KIND,), recipients=(self.device_pubkey,))]
        )
        return [e for e in events if e.id not in handled and e.id not in self._started_events]

    async def receive_pending(self, engine: WorkflowEngine, library: WorkflowLibrary) -> list[str]:
        """Start one *Skill Receive* process per new event; returns the process ids."""
        started = []
        owner = await library.refresh_owner()
        for event in await self.pending_events(library):
            properties: dict[str, Any] = {"skill_event": event.to_dict()}
            if owner is not None:
                properties["__user_id__"] = owner
            self._started_events.add(event.id)
            definition = library.get_workflow(SKILL_RECEIVE_WORKFLOW)
            process = await engine.create_process(definition, properties=properties)
            await engine.start_process(process.id)
            started.append(process.id)
        return started

    def apply_received(
        self, library: WorkflowLibrary, verified: SkillVerification
    ) -> dict[str, Any]:
        """Merge a verified, gated ``SKILL`` into the library by lineage.

        Returns ``{action, name, fork_name, local_sha256, incoming_sha256}`` with action
        ``new`` / ``fast_forward`` (saved), ``noop`` / ``stale`` (nothing saved) or ``fork``
        (saved as ``<name> (from <sphere>)``, ``fork_of`` set on both copies).

        Raises:
            zebra_agent.library.AdoptionRefused: The library refused the save.
        """
        if not verified.ok or verified.yaml is None or verified.commons is None:
            raise SkillRefused(f"SKILL did not verify ({verified.reason})")
        name = verified.name or "untitled"
        incoming = verified.commons
        incoming_hash = verified.content_sha256
        local_block = library.commons_block(name) if library._files_named(name) else None
        local_hash = (local_block or {}).get("content_sha256")
        action = merge_decision(local_block, incoming)
        fork_name = None
        if action in (NEW, FAST_FORWARD):
            library.save(
                verified.yaml,
                writer="adopt",
                received=incoming,
                expected_sha256=incoming_hash,
                name=name,
                sync=True,
                replace=action == FAST_FORWARD,
                reason=f"synced from {verified.sender_sphere}",
            )
        elif action == FORK:
            fork_name = f"{name} (from {verified.sender_sphere})"
            library.save(
                verified.yaml,
                writer="adopt",
                received=incoming,
                expected_sha256=incoming_hash,
                name=fork_name,
                sync=True,
                fork_of=local_hash,
                reason=f"synced from {verified.sender_sphere}; forked from this device's copy",
            )
            library.set_fork_of(name, incoming_hash)
        record_share(
            library,
            name,
            incoming_hash,
            verified.sender_sphere or "?",
            RECEIVED,
            reason=action,
            event_id=verified.event_id,
        )
        return {
            "action": action,
            "name": name,
            "fork_name": fork_name,
            "local_sha256": local_hash,
            "incoming_sha256": incoming_hash,
        }

    def verify(self, event: Event, now: int | None = None) -> SkillVerification:
        """``verify_skill`` with this device's identity."""
        return verify_skill(
            event,
            device_pubkey=self.device_pubkey,
            zebra_pubkey=self.zebra_pubkey,
            sphere=self.sphere,
            held_events=self.held_events(),
            now=int(time.time()) if now is None else now,
        )
