"""Layout for the private genealogy page (#238).

Turns a ``zebra_agent.genealogy.Genealogy`` into template context: an inline SVG
layered DAG (oldest at the top, one row per layer; drawn by ``api/dag_svg.py``,
shared with the public genealogy, #247) and the version cards. No JavaScript.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zebra_agent.genealogy import Genealogy, Version

from zebra_agent_web.api.dag_svg import DagEdge, DagNode, dag_svg
from zebra_agent_web.api.thoughts import Thought

# Which recorded reason a source is, as the page names it.
REASON_LABELS = {
    "evaluator": "Dream cycle evaluation",
    "selector": "Workflow choice",
}


def anchor(version: Version) -> str:
    """The version card's id on the page."""
    return f"v-{version.short}"


def _colours(version: Version) -> tuple[str, str, str]:
    """(stroke, text, dash) for a node: current ok, retired / hash-only faint."""
    if version.hash_only:
        return "var(--color-faint)", "var(--color-faint)", "4 3"
    if version.current:
        return "var(--color-ok)", "var(--color-ink)", ""
    if version.retired is not None and not version.active:
        return "var(--color-line)", "var(--color-muted)", ""
    return "var(--color-muted)", "var(--color-ink)", ""


def _node_title(version: Version) -> str:
    parts = [version.short]
    if version.name:
        parts.append(version.name)
    parts.append(version.writer_label if not version.hash_only else "no file on this device")
    if version.current:
        parts.append("current")
    elif version.retired is not None and not version.active:
        parts.append("retired")
    return ", ".join(parts)


def genealogy_svg(genealogy: Genealogy) -> str:
    """The lineage as an inline SVG, parents above children (shared ``dag_svg``)."""
    nodes = []
    for v in genealogy.versions:
        stroke, text, dash = _colours(v)
        label = "no file here" if v.hash_only else v.writer_label
        nodes.append(
            DagNode(
                key=v.key,
                layer=v.layer,
                order=v.order,
                line1=v.short,
                line2=f"{label}{' · current' if v.current else ''}",
                title=_node_title(v),
                href=None if v.hash_only else f"#{anchor(v)}",
                stroke=stroke,
                text=text,
                dash=dash,
                strong=v.current,
            )
        )
    return dag_svg(
        nodes,
        [DagEdge(p, c) for p, c in genealogy.edges],
        f"Lineage of {genealogy.name}: {len(nodes)} versions",
        marker="gen-arrow",
    )


@dataclass
class DiffLine:
    kind: str  # add / remove / hunk / context
    text: str


def diff_lines(diff: str | None) -> list[DiffLine]:
    """A unified diff as lines the template can style (file headers dropped)."""
    out: list[DiffLine] = []
    for line in (diff or "").splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("@@"):
            kind = "hunk"
        elif line.startswith("+"):
            kind = "add"
        elif line.startswith("-"):
            kind = "remove"
        else:
            kind = "context"
        out.append(DiffLine(kind, line))
    return out


def reason_thought(reason: dict[str, str] | None) -> Thought | None:
    """A recorded reason as a voice-layer thought; None when none was recorded."""
    if not reason:
        return None
    return Thought(
        kind="genealogy",
        label=REASON_LABELS.get(reason.get("source", ""), "Recorded reason"),
        task_id="",
        text=reason["text"],
        is_voice=reason.get("kind") == "voice",
        confidence=None,
    )


def _hit_kinds(leak: dict[str, Any] | None) -> list[str]:
    kinds: dict[str, int] = {}
    for hit in (leak or {}).get("hits") or []:
        kinds[hit.get("kind", "?")] = kinds.get(hit.get("kind", "?"), 0) + 1
    return [f"{n} {kind}" for kind, n in sorted(kinds.items())]


def genealogy_context(genealogy: Genealogy) -> dict[str, Any]:
    """Template context for ``pages/workflow_genealogy.html``."""
    by_key = {v.key: v for v in genealogy.versions}
    cards = []
    for v in genealogy.versions:
        parents = [by_key[p] for p in v.parents if p in by_key]
        cards.append(
            {
                "v": v,
                "anchor": anchor(v),
                "parents": [{"short": p.short, "anchor": anchor(p)} for p in parents],
                "children": [
                    {"short": by_key[c].short, "anchor": anchor(by_key[c])}
                    for c in v.children
                    if c in by_key
                ],
                "thought": reason_thought(v.reason),
                "diff": diff_lines(v.diff),
                "hit_kinds": _hit_kinds(v.leak_guard),
                "other_names": [n for n in v.names if n != genealogy.name],
            }
        )
    rejected = [{**r, "hit_kinds": _hit_kinds(r.get("leak_guard"))} for r in genealogy.rejected]
    for r in rejected:
        r["thought"] = reason_thought(r.get("reason"))
    return {
        "workflow_name": genealogy.name,
        "graph_svg": genealogy_svg(genealogy),
        "cards": cards,
        "version_count": sum(1 for v in genealogy.versions if not v.hash_only),
        "hash_only_count": sum(1 for v in genealogy.versions if v.hash_only),
        "rejected": rejected,
        "share_status": genealogy.share_status,
        "forks": genealogy.forks,
    }
