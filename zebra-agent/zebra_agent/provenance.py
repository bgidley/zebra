"""Workflow provenance for the Zebra Commons (#229, S2a).

Every workflow file the library writes carries a ``commons`` block, set only by
``WorkflowLibrary.save()``: the canonical content hash, its lineage, the spheres
whose run data shaped it and whether any other user's runs did. See
``specs/zebra-commons-design.md`` § Workflow provenance.

This module is pure (no I/O, no Django): hashing, reading and writing the block,
the writer's ``Exposure`` and the local-change rules (``next_block``).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

COMMONS_KEY = "commons"
ANCESTOR_WINDOW = 32
# Local bookkeeping tags: not part of the content (adoption must not change the hash).
LOCAL_TAGS = frozenset({"llm-defined", "system"})
DEFAULT_SPHERE = "local"

# Every key of the block, in the order it is written.
BLOCK_KEYS = (
    "content_sha256",
    "parent_sha256",
    "ancestors",
    "origin_pubkey",
    "fork_of",
    "adopted_at",
    "supervised",
    "sphere",
    "tainted_by",
    "share_with",
    "foreign_users",
)


class NotHashableError(ValueError):
    """The workflow has no JSON form, so it has no canonical hash."""


class _CanonicalLoader(yaml.SafeLoader):
    """SafeLoader without the timestamp resolver: ``2026-01-01`` stays a string."""


_CanonicalLoader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _check_json(value: Any, path: str = "") -> None:
    """Raise ``NotHashableError`` unless *value* is plain JSON data."""
    if value is None or isinstance(value, bool | str | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise NotHashableError(f"non-finite number at {path or 'top level'}")
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _check_json(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise NotHashableError(f"non-string key {key!r} at {path or 'top level'}")
            _check_json(item, f"{path}.{key}" if path else key)
        return
    raise NotHashableError(f"{type(value).__name__} value at {path or 'top level'}")


def canonical_content(yaml_content: str) -> dict[str, Any]:
    """The hashed part of a workflow: no ``commons`` block, no ``name``, no local tags.

    Raises:
        NotHashableError: If the YAML does not parse to a mapping of JSON values.
    """
    try:
        data = yaml.load(yaml_content, Loader=_CanonicalLoader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as e:
        raise NotHashableError(f"invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise NotHashableError("not a mapping")
    data = {k: v for k, v in data.items() if k not in (COMMONS_KEY, "name")}
    tags = data.get("tags")
    if isinstance(tags, list):
        tags = [t for t in tags if t not in LOCAL_TAGS]
        if tags:
            data["tags"] = tags
        else:
            data.pop("tags")
    _check_json(data)
    return data


def content_sha256(yaml_content: str) -> str:
    """Hex sha256 of the workflow's canonical content.

    Raises:
        NotHashableError: If the workflow has no JSON form.
    """
    canonical = json.dumps(
        canonical_content(yaml_content),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def try_content_sha256(yaml_content: str) -> tuple[str | None, str | None]:
    """``(hash, None)``, or ``(None, reason)`` when the workflow is not hashable."""
    try:
        return content_sha256(yaml_content), None
    except NotHashableError as e:
        return None, str(e)


def read_commons(yaml_content: str) -> dict[str, Any] | None:
    """The workflow's ``commons`` block, or None if it has none (or does not parse)."""
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError:
        return None
    block = data.get(COMMONS_KEY) if isinstance(data, dict) else None
    return block if isinstance(block, dict) else None


# A column-0 ``commons:`` line up to the next column-0 key (comments and blank
# lines inside the block belong to it).
_BLOCK_RE = re.compile(r"^commons:.*?(?=^[^\s#]|\Z)", re.MULTILINE | re.DOTALL)


def _parse(yaml_content: str) -> Any:
    try:
        return yaml.safe_load(yaml_content)
    except yaml.YAMLError:
        return None


def strip_commons(yaml_content: str) -> str:
    """The workflow YAML without its ``commons`` block (unchanged if it has none).

    The block is cut out of the text so comments and layout survive; if that does
    not give the same data, the YAML is dumped again without it.
    """
    data = _parse(yaml_content)
    if not isinstance(data, dict) or COMMONS_KEY not in data:
        return yaml_content
    expected = {k: v for k, v in data.items() if k != COMMONS_KEY}
    stripped = _BLOCK_RE.sub("", yaml_content)
    if _parse(stripped) == expected:
        return stripped
    return yaml.safe_dump(expected, sort_keys=False, allow_unicode=True, width=100)


def with_commons(yaml_content: str, block: dict[str, Any]) -> str:
    """The YAML (without any block) with *block* appended as the last top-level key."""
    body = strip_commons(yaml_content).rstrip("\n") + "\n"
    ordered = {key: block.get(key) for key in BLOCK_KEYS}
    return body + yaml.safe_dump({COMMONS_KEY: ordered}, sort_keys=False, allow_unicode=True)


@dataclass
class Exposure:
    """What an LLM writer was shown, travelling with its write to ``save()``.

    Attributes:
        run_texts: Other runs' content (leak guard, full check)
        goal_texts: The goal the workflow is written for (leak guard, long phrases)
        allow_text: Text Zebra supplied (system prompt, action list); never a leak
        user_ids: Users whose runs or goal the writer saw (``foreign_users``)
        reject: A leak-guard hit refuses the save (dream cycle); otherwise it is kept
        foreign_users: Taint carried in by other library workflows the writer was
            shown (one of them is ``foreign_users``), so it cannot be laundered
            through a new lineage
        tainted_by: Spheres from the ``tainted_by`` of the workflows the writer was shown
    """

    run_texts: list[str] = field(default_factory=list)
    goal_texts: list[str] = field(default_factory=list)
    allow_text: str = ""
    user_ids: list[int] = field(default_factory=list)
    reject: bool = False
    foreign_users: bool = False
    tainted_by: list[str] = field(default_factory=list)

    def with_shown(self, blocks: list[dict[str, Any] | None]) -> Exposure:
        """Fold in the taint of library workflows the writer was shown (#229).

        Unknown provenance fails closed: a shown workflow with no block (None, or
        anything that is not a mapping) counts as ``foreign_users``. Pass
        ``WorkflowLibrary.commons_block()``, which gives an unmodified built-in a
        clean block and any other blockless file ``legacy_block()``.

        Args:
            blocks: The shown workflows' ``commons`` blocks

        Returns:
            Self, with ``foreign_users`` OR-ed and ``tainted_by`` extended.
        """
        for block in blocks:
            if not isinstance(block, dict):
                self.foreign_users = True
                continue
            if block.get("foreign_users"):
                self.foreign_users = True
            for sphere in block.get("tainted_by") or []:
                if isinstance(sphere, str) and sphere not in self.tainted_by:
                    self.tainted_by.append(sphere)
        return self

    @property
    def has_texts(self) -> bool:
        return any(t.strip() for t in [*self.run_texts, *self.goal_texts] if isinstance(t, str))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_texts": list(self.run_texts),
            "goal_texts": list(self.goal_texts),
            "allow_text": self.allow_text,
            "user_ids": list(self.user_ids),
            "reject": self.reject,
            "foreign_users": self.foreign_users,
            "tainted_by": list(self.tainted_by),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Exposure | None:
        if not isinstance(data, dict):
            return None
        return cls(
            run_texts=[str(t) for t in data.get("run_texts") or []],
            goal_texts=[str(t) for t in data.get("goal_texts") or []],
            allow_text=str(data.get("allow_text") or ""),
            user_ids=user_ids(data.get("user_ids")),
            reject=bool(data.get("reject", False)),
            foreign_users=bool(data.get("foreign_users", False)),
            tainted_by=[t for t in data.get("tainted_by") or [] if isinstance(t, str)],
        )


def user_ids(values: Any) -> list[int]:
    """Distinct integer user ids from a list (None and junk dropped), sorted."""
    found = set()
    for value in values or []:
        try:
            found.add(int(value))
        except (TypeError, ValueError):
            continue
    return sorted(found)


def has_foreign_users(ids: list[int], owner_user_id: int | None) -> bool:
    """True when *ids* holds a user other than the owner; any user while it is unknown."""
    if owner_user_id is None:
        return bool(ids)
    return any(uid != owner_user_id for uid in ids)


def legacy_block(*, builtin: bool) -> dict[str, Any]:
    """The provenance of a workflow file written before #229, which has no block.

    Its history is unknown: the dream cycle may have rewritten it from other users'
    runs. Only an unmodified built-in (the content hash of a shipped workflow) is
    known clean; any other blockless file is ``foreign_users`` (fail closed). Never
    written to disk: the next ``WorkflowLibrary.save()`` gives it a real block.
    """
    return {"foreign_users": not builtin, "tainted_by": [], "legacy": True}


def next_block(
    *,
    new_hash: str | None,
    parent_block: dict[str, Any] | None,
    parent_hash: str | None,
    has_parent: bool,
    sphere: str,
    foreign: bool,
    parent_unknown: bool = False,
) -> dict[str, Any]:
    """The ``commons`` block for a local save (the design's local-change rules).

    Args:
        new_hash: Hash of the saved content (None when it is not hashable)
        parent_block: The parent's block, if it has one
        parent_hash: The parent's hash (its block's, else computed from its content)
        has_parent: Whether the save has a parent workflow at all
        sphere: This library's sphere
        foreign: The writer's exposure held another user's runs
        parent_unknown: The parent has no block and is not an unmodified built-in,
            so its lineage may have seen other users' runs: the result is
            ``foreign_users`` (a first save never launders taint)
    """
    parent_block = parent_block or {}
    inherited_foreign = bool(parent_block.get("foreign_users")) or (has_parent and parent_unknown)
    if has_parent and new_hash is not None and new_hash == parent_hash and parent_block:
        # Unchanged content: same provenance (a taint the writer adds still counts).
        block = {key: parent_block.get(key) for key in BLOCK_KEYS}
        block["foreign_users"] = inherited_foreign or foreign
        return block
    if not has_parent:
        return {
            "content_sha256": new_hash,
            "parent_sha256": None,
            "ancestors": [],
            "origin_pubkey": None,
            "fork_of": None,
            "adopted_at": None,
            "supervised": False,
            "sphere": sphere,
            "tainted_by": [sphere],
            "share_with": [],
            "foreign_users": foreign,
        }
    if new_hash is not None and new_hash == parent_hash:
        ancestors = list(parent_block.get("ancestors") or [])
        parent_sha = parent_block.get("parent_sha256")
    else:
        ancestors = [parent_hash] if parent_hash else []
        ancestors += [a for a in parent_block.get("ancestors") or [] if a != parent_hash]
        parent_sha = parent_hash
    tainted = [s for s in parent_block.get("tainted_by") or [] if isinstance(s, str)]
    if sphere not in tainted:
        tainted.append(sphere)
    return {
        "content_sha256": new_hash,
        "parent_sha256": parent_sha,
        "ancestors": ancestors[:ANCESTOR_WINDOW],
        "origin_pubkey": None,
        "fork_of": parent_block.get("fork_of"),
        "adopted_at": parent_block.get("adopted_at"),
        "supervised": bool(parent_block.get("supervised", False)),
        "sphere": parent_block.get("sphere") or sphere,
        "tainted_by": tainted,
        "share_with": [],
        "foreign_users": inherited_foreign or foreign,
    }


class _ExportDumper(yaml.SafeDumper):
    """SafeDumper writing multi-line strings (prompts) as ``|`` blocks."""


def _block_str(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_ExportDumper.add_representer(str, _block_str)


def relabel(yaml_content: str, *, name: str | None = None) -> str:
    """The workflow YAML without its ``commons`` block and local tags, optionally renamed.

    What travels between Zebras (export, adoption, #229 S2b): the block is re-attached by
    the receiving library and local tags (``llm-defined``, ``system``) are bookkeeping of
    the sender. Neither the name nor these tags is hashed, so ``content_sha256`` is
    unchanged. The YAML is re-dumped only when something changes.

    Raises:
        NotHashableError: If the YAML does not parse to a mapping.
    """
    yaml_content = strip_commons(yaml_content)
    try:
        data = yaml.load(yaml_content, Loader=_CanonicalLoader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as e:
        raise NotHashableError(f"invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise NotHashableError("not a mapping")
    changed = False
    if name is not None and data.get("name") != name:
        data["name"] = name
        changed = True
    tags = data.get("tags")
    if isinstance(tags, list) and any(t in LOCAL_TAGS for t in tags):
        kept = [t for t in tags if t not in LOCAL_TAGS]
        if kept:
            data["tags"] = kept
        else:
            data.pop("tags")
        changed = True
    if not changed:
        return yaml_content
    return yaml.dump(data, Dumper=_ExportDumper, sort_keys=False, allow_unicode=True, width=100)


def adopted_block(
    received: dict[str, Any],
    *,
    sphere: str,
    adopted_at: str,
    origin_pubkey: str | None = None,
) -> dict[str, Any]:
    """The block for an adopted or synced workflow (``save(writer="adopt")``, #229 S2b).

    The received block is kept verbatim (hash, lineage, ``tainted_by``,
    ``foreign_users``, ``fork_of``): adoption is not a local change. Only local
    bookkeeping changes: ``sphere`` (this library's), ``share_with: []`` (each share
    is decided again here), ``adopted_at``, ``supervised: true`` (until a human clears
    it) and ``origin_pubkey`` when the block has none (the publisher's Zebra key).
    """
    block = {key: received.get(key) for key in BLOCK_KEYS}
    block["sphere"] = sphere
    block["share_with"] = []
    block["adopted_at"] = adopted_at
    block["supervised"] = True
    if not block.get("origin_pubkey") and origin_pubkey:
        block["origin_pubkey"] = origin_pubkey
    return block
