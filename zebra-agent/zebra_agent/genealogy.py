"""Private skill genealogy (#238): the local change journal and the lineage DAG.

``WorkflowLibrary.save()`` appends one record per save to a local journal
(``<library>/.lineage/journal.jsonl``): who wrote the version, when, on which
sphere and device, the reason the writer recorded and the leak-guard status.
These are local facts: they never go in the ``commons`` block and never leave
the deployment. Leak-guard hit *text* is dropped before writing.

``build_genealogy(library, name)`` reads the active and retired workflow files
and the journal and returns the lineage of one workflow as a DAG over content
hashes (``commons.parent_sha256``, ``ancestors``, ``fork_of``). Nothing here
calls an LLM or invents a reason: a version whose writer recorded none has
``reason`` None.

No Django: the web page (``zebra_agent_web.api.genealogy_view``) lays it out.
"""

from __future__ import annotations

import difflib
import json
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from zebra_agent.provenance import read_commons, strip_commons, try_content_sha256

if TYPE_CHECKING:
    from zebra_agent.library import WorkflowLibrary

logger = logging.getLogger(__name__)

JOURNAL_DIR = ".lineage"
JOURNAL_FILE = "journal.jsonl"
JOURNAL_VERSION = 1

SAVED = "saved"
REJECTED = "rejected"

# The writer names save() is given, as the page labels them (design § Genealogy view).
WRITER_LABELS = {
    "creator": "creator",
    "variant_creator": "variant",
    "optimizer": "optimizer",
    "gym": "optimizer",
    "human": "human",
    "adopt": "adopted",
    "sync": "synced",
    "builtin": "built-in",
}
UNKNOWN_WRITER = "unknown"

# A diff longer than this is cut (the page shows it behind a disclosure).
MAX_DIFF_LINES = 400
# A reason longer than this is cut when journaled.
MAX_REASON_CHARS = 2000

_RETIRED_MARKER = "\n# --- retired by zebra (#148) ---\n"


def writer_label(writer: str | None) -> str:
    """The page's label for a ``save()`` writer (``unknown`` when none is known)."""
    return WRITER_LABELS.get(writer or "", UNKNOWN_WRITER)


def normalize_reason(reason: str | dict | None) -> dict[str, str] | None:
    """A writer's reason as ``{text, kind, source}``; None when it gave none.

    A string is recorded reasoning (kind ``reasoning``). A dict may say kind
    ``voice`` (Zebra's own first-person line) and its ``source``.
    """
    if isinstance(reason, str):
        reason = {"text": reason}
    if not isinstance(reason, dict):
        return None
    text = " ".join(str(reason.get("text") or "").split())
    if not text:
        return None
    kind = reason.get("kind") if reason.get("kind") in ("voice", "reasoning") else "reasoning"
    out = {"text": text[:MAX_REASON_CHARS], "kind": kind}
    if reason.get("source"):
        out["source"] = str(reason["source"])[:40]
    return out


def scrub_leak(leak: dict | None) -> dict[str, Any] | None:
    """A leak-guard record without the hit text (kind, location and source only)."""
    if not isinstance(leak, dict) or not leak.get("status"):
        return None
    hits = [
        {
            "kind": str(h.get("kind", "")),
            "where": str(h.get("where", ""))[:200],
            "source": str(h.get("source", "")),
        }
        for h in leak.get("hits") or []
        if isinstance(h, dict)
    ]
    out: dict[str, Any] = {"status": str(leak["status"]), "hits": hits}
    if leak.get("error") or leak.get("check_failed"):
        out["check_failed"] = True  # the error text may quote the content
    if leak.get("save_check"):
        out["save_check"] = str(leak["save_check"])  # the save-time result (#236: kept = tainted)
    return out


def merge_leak(writer_leak: dict | None, save_leak: dict | None) -> dict[str, Any] | None:
    """The writer's leak record plus the hits the save-time check kept."""
    writer_leak, save_leak = scrub_leak(writer_leak), scrub_leak(save_leak)
    if writer_leak is None or save_leak is None:
        return writer_leak or save_leak
    seen = {(h["kind"], h["where"], h["source"]) for h in writer_leak["hits"]}
    extra = [h for h in save_leak["hits"] if (h["kind"], h["where"], h["source"]) not in seen]
    merged = {**writer_leak, "hits": writer_leak["hits"] + extra, "save_check": save_leak["status"]}
    if save_leak.get("check_failed"):
        merged["check_failed"] = True
    return merged


def journal_record(
    *,
    event: str,
    name: str,
    file: str | None,
    writer: str,
    content_sha256: str | None,
    parent_sha256: str | None,
    parent_name: str | None,
    sphere: str | None,
    device: str | None,
    reason: str | dict | None,
    leak: dict | None,
    at: datetime | None = None,
) -> dict[str, Any]:
    """One journal line (see the module docstring)."""
    return {
        "v": JOURNAL_VERSION,
        "at": (at or datetime.now(UTC)).isoformat(timespec="microseconds"),
        "event": event,
        "name": name,
        "file": file,
        "writer": writer,
        "content_sha256": content_sha256,
        "parent_sha256": parent_sha256,
        "parent_name": parent_name,
        "sphere": sphere,
        "device": device,
        "reason": normalize_reason(reason),
        "leak_guard": scrub_leak(leak),
    }


class LineageJournal:
    """Append-only JSON-lines journal of workflow saves, local to this library."""

    def __init__(self, library_path: Path):
        self.path = Path(library_path) / JOURNAL_DIR / JOURNAL_FILE

    def append(self, record: dict[str, Any]) -> None:
        """Append *record*; a failure is logged and never blocks the save."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except (OSError, TypeError, ValueError) as e:
            logger.warning("Could not write the lineage journal (%s): %s", self.path, e)

    def read(self) -> list[dict[str, Any]]:
        """Every readable record, oldest first; bad lines are skipped."""
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        except OSError as e:
            logger.warning("Could not read the lineage journal (%s): %s", self.path, e)
            return []
        records = []
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                records.append(record)
        return records


# --- the lineage DAG -------------------------------------------------------------------


@dataclass
class _File:
    """One workflow file on this device, active or retired."""

    path: Path
    name: str
    yaml: str  # without the commons block and the retirement metadata
    block: dict[str, Any] | None
    key: str  # content hash, else ``file:<stem>``
    hashed: bool
    retired: dict[str, Any] | None
    mtime: datetime

    @property
    def parent(self) -> str | None:
        value = (self.block or {}).get("parent_sha256")
        return value if isinstance(value, str) and value else None

    @property
    def ancestors(self) -> list[str]:
        values = (self.block or {}).get("ancestors") or []
        return [a for a in values if isinstance(a, str) and a]

    @property
    def fork_of(self) -> str | None:
        value = (self.block or {}).get("fork_of")
        return value if isinstance(value, str) and value else None

    @property
    def lineage(self) -> set[str]:
        out = set(self.ancestors)
        out.update(v for v in (self.parent, self.fork_of) if v)
        out.discard(self.key)
        return out


@dataclass
class Version:
    """One version (content hash) in a workflow's lineage."""

    key: str
    hashed: bool = True
    hash_only: bool = False  # an ancestor with no file on this device
    names: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    current: bool = False
    active: bool = False
    retired: dict[str, Any] | None = None
    at: datetime | None = None
    date_source: str | None = None  # ``journal`` or ``file``
    writer: str | None = None
    sphere: str | None = None
    device: str | None = None
    legacy: bool = False  # the file has no commons block (written before #229)
    tainted_by: list[str] = field(default_factory=list)
    foreign_users: bool = False
    fork_of: str | None = None
    leak_guard: dict[str, Any] | None = None
    reason: dict[str, str] | None = None
    parents: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    diff: str | None = None
    diff_truncated: bool = False
    layer: int = 0
    order: int = 0
    yaml: str | None = field(default=None, repr=False)

    @property
    def short(self) -> str:
        return self.key.removeprefix("file:")[:12]

    @property
    def writer_label(self) -> str:
        return writer_label(self.writer)

    @property
    def name(self) -> str | None:
        return self.names[0] if self.names else None


@dataclass
class Genealogy:
    """The lineage of one workflow (``build_genealogy``)."""

    name: str
    versions: list[Version]  # newest first; hash-only ancestors last
    edges: list[tuple[str, str]]  # (parent key, child key)
    current: str | None
    rejected: list[dict[str, Any]] = field(default_factory=list)  # refused saves, newest first
    # Skill sync (#236): the current version's status per sphere (journal share
    # records and ``share_with``) and the sync forks waiting for a choice.
    share_status: list[dict[str, Any]] = field(default_factory=list)
    forks: list[dict[str, Any]] = field(default_factory=list)

    @property
    def layers(self) -> int:
        return max((v.layer for v in self.versions), default=-1) + 1

    def version(self, key: str) -> Version | None:
        return next((v for v in self.versions if v.key == key), None)


def _read_files(library: WorkflowLibrary) -> list[_File]:
    """Every parseable workflow file, active then retired, newest first within each."""
    files: list[_File] = []
    for directory, retired in ((library.library_path, False), (library.retired_path, True)):
        if not directory.is_dir():
            continue
        for path in directory.glob("*.yaml"):
            try:
                raw = path.read_text()
                body, _, meta_text = raw.partition(_RETIRED_MARKER)
                data = yaml.safe_load(body)
                if not isinstance(data, dict) or not data.get("name"):
                    continue
                meta = (yaml.safe_load(meta_text) or {}).get("retired") if meta_text else None
                mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            except Exception:  # noqa: BLE001 - an unreadable file is not part of any lineage
                continue
            block = read_commons(body)
            content_hash = (block or {}).get("content_sha256")
            if not content_hash:
                content_hash, _ = try_content_sha256(body)
            files.append(
                _File(
                    path=path,
                    name=str(data["name"]),
                    yaml=strip_commons(body),
                    block=block,
                    key=content_hash or f"file:{'retired/' if retired else ''}{path.stem}",
                    hashed=bool(content_hash),
                    retired=(meta if isinstance(meta, dict) else {}) if retired else None,
                    mtime=mtime,
                )
            )
    files.sort(key=lambda f: (f.retired is not None, -f.mtime.timestamp()))
    return files


def _family(files: list[_File], name: str) -> tuple[list[_File], set[str]]:
    """The files linked to workflow *name* by hash, and every hash in their lineage."""
    members = [f for f in files if f.name == name]
    keys = {f.key for f in members}
    lineage = set().union(*(f.lineage for f in members)) if members else set()
    changed = True
    while changed:
        changed = False
        for f in files:
            if f in members:
                continue
            if f.key in keys or f.key in lineage or f.lineage & keys:
                members.append(f)
                keys.add(f.key)
                lineage |= f.lineage
                changed = True
    return members, lineage | keys


def _parse_at(value: Any) -> datetime | None:
    try:
        at = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def _diff(parent: str, child: str, parent_label: str, child_label: str) -> tuple[str, bool]:
    lines = list(
        difflib.unified_diff(
            parent.splitlines(),
            child.splitlines(),
            fromfile=parent_label,
            tofile=child_label,
            lineterm="",
        )
    )
    return "\n".join(lines[:MAX_DIFF_LINES]), len(lines) > MAX_DIFF_LINES


def layer_dag(
    parents: Mapping[str, Iterable[str]], sort_key: Callable[[str], Any]
) -> dict[str, tuple[int, int]]:
    """``{key: (layer, order)}`` for a DAG given each node's parents (shared with #247).

    Layer = longest path from a root; within a layer, by *sort_key* (oldest first).
    The graph may have a cycle (a revert to earlier content, or mutual trust); a
    node stuck in one is placed after the parents already placed, breaking the
    cycle at the smallest *sort_key*. Parents that are not nodes are ignored.
    """
    pending = {k: {p for p in ps if p in parents} for k, ps in parents.items()}
    placed: dict[str, int] = {}
    while len(placed) < len(pending):
        ready = [k for k in pending if k not in placed and pending[k] <= placed.keys()]
        if not ready:  # a cycle: break it at its smallest node
            ready = [min((k for k in pending if k not in placed), key=sort_key)]
        for key in ready:
            known = [placed[p] for p in pending[key] if p in placed]
            placed[key] = max(known) + 1 if known else 0
    by_layer: dict[int, list[str]] = {}
    for key, layer in placed.items():
        by_layer.setdefault(layer, []).append(key)
    out: dict[str, tuple[int, int]] = {}
    for layer, keys in by_layer.items():
        for order, key in enumerate(sorted(keys, key=sort_key)):
            out[key] = (layer, order)
    return out


def _layout(versions: dict[str, Version]) -> None:
    """Place each version (``layer_dag``): oldest first within a layer."""
    placed = layer_dag(
        {k: v.parents for k, v in versions.items()},
        lambda k: (versions[k].at or datetime.max.replace(tzinfo=UTC), k),
    )
    for key, (layer, order) in placed.items():
        versions[key].layer, versions[key].order = layer, order


def build_genealogy(library: WorkflowLibrary, name: str) -> Genealogy | None:
    """The lineage of workflow *name* on this device, or None when there is no such file.

    Args:
        library: The workflow library (its active and retired files and journal).
        name: The workflow name.

    Returns:
        A ``Genealogy`` with one ``Version`` per content hash linked to the workflow
        (variants under other names included), or None.
    """
    library.ensure_initialized()
    library.quarantine_unparseable()
    files = _read_files(library)
    members, lineage = _family(files, name)
    if not any(f.name == name for f in members):
        return None
    records = LineageJournal(library.library_path).read()
    saved = [r for r in records if r.get("event") == SAVED]
    builtin = library.builtin_hashes()

    versions: dict[str, Version] = {}
    for f in members:  # newest first: the first file for a key is the one displayed
        version = versions.setdefault(f.key, Version(key=f.key, hashed=f.hashed))
        if f.name not in version.names:
            version.names.append(f.name)
        rel = f"retired/{f.path.name}" if f.retired is not None else f.path.name
        version.files.append(rel)
        if f.retired is None:
            version.active = True
        if version.yaml is None:
            version.yaml = f.yaml
            version.retired = f.retired
            version.legacy = f.block is None
            block = f.block or {}
            version.sphere = block.get("sphere")
            version.tainted_by = [s for s in block.get("tainted_by") or [] if isinstance(s, str)]
            version.foreign_users = bool(block.get("foreign_users"))
            version.fork_of = f.fork_of
            version.at, version.date_source = f.mtime, "file"
        if f.retired is None:
            version.retired = None  # an active copy of the same content
    for key in lineage - versions.keys():
        versions[key] = Version(key=key, hash_only=True)

    edges: set[tuple[str, str]] = set()
    for f in members:
        if f.parent and f.parent != f.key:
            edges.add((f.parent, f.key))
        chain = f.ancestors
        for child, parent in zip(chain, chain[1:], strict=False):
            if child != parent:
                edges.add((parent, child))
    for parent, child in sorted(edges):
        if parent in versions and child in versions:
            if parent not in versions[child].parents:
                versions[child].parents.append(parent)
            versions[parent].children.append(child)

    for key, version in versions.items():
        # The first save that produced this content says who made it and why.
        if version.hashed:
            mine = [r for r in saved if r.get("content_sha256") == key]
        else:
            mine = [r for r in saved if r.get("file") in version.files]
        if mine:
            record = mine[0]
            version.writer = record.get("writer")
            version.device = record.get("device")
            version.sphere = version.sphere or record.get("sphere")
            version.reason = normalize_reason(record.get("reason"))
            version.leak_guard = scrub_leak(record.get("leak_guard"))
            at = _parse_at(record.get("at"))
            if at is not None:
                version.at, version.date_source = at, "journal"
        elif version.hashed and key in builtin:
            version.writer = "builtin"

    for version in versions.values():
        parent = versions.get(version.parents[0]) if version.parents else None
        if parent is not None and parent.yaml is not None and version.yaml is not None:
            version.diff, version.diff_truncated = _diff(
                parent.yaml, version.yaml, parent.short, version.short
            )

    current = next((f.key for f in files if f.name == name and f.retired is None), None)
    if current is None:
        current = next(f.key for f in members if f.name == name)
    versions[current].current = True

    _layout(versions)
    far_past = datetime.min.replace(tzinfo=UTC)
    ordered = sorted(
        versions.values(), key=lambda v: (v.hash_only, -(v.at or far_past).timestamp(), v.key)
    )
    names = {n for v in versions.values() for n in v.names}
    rejected = [
        r
        for r in reversed(records)
        if r.get("event") == REJECTED and (r.get("name") in names or r.get("parent_name") in names)
    ]
    for r in rejected:
        r["at_dt"] = _parse_at(r.get("at"))
        r["reason"] = normalize_reason(r.get("reason"))
        r["leak_guard"] = scrub_leak(r.get("leak_guard"))
        r["writer_label"] = writer_label(r.get("writer"))
    from zebra_agent.commons.sync import share_status

    current_file = next((f for f in files if f.name == name and f.retired is None), None)
    current_block = current_file.block if current_file is not None else None
    forks = [
        {
            "fork_name": f.name,
            "of": name,
            "summary": f"{f.name} forked from {name}: both changed, waiting for your choice",
        }
        for f in members
        if f.retired is None and f.fork_of and f.name != name
    ]
    return Genealogy(
        name=name,
        versions=ordered,
        edges=sorted((p, c) for p, c in edges if p in versions and c in versions),
        current=current,
        rejected=rejected,
        share_status=share_status(
            library, name, (current_block or {}).get("content_sha256"), current_block
        ),
        forks=forks,
    )
