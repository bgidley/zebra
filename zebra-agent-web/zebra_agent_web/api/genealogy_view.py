"""Layout for the private genealogy page (#238).

Turns a ``zebra_agent.genealogy.Genealogy`` into template context: an inline SVG
layered DAG (oldest at the top, one row per layer) and the version cards. No
JavaScript. Colours are theme tokens through CSS variables, so the graph
follows light and dark like the rest of the page (``specs/web-ui-design.md``).
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any

from zebra_agent.genealogy import Genealogy, Version

from zebra_agent_web.api.thoughts import Thought

NODE_W = 132
NODE_H = 46
GAP_X = 20
GAP_Y = 34
PAD = 8

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
    """The lineage as an inline SVG, parents above children."""
    versions = {v.key: v for v in genealogy.versions}
    if not versions:
        return ""
    width_nodes = max(v.order for v in versions.values()) + 1
    layers = genealogy.layers
    width = PAD * 2 + width_nodes * NODE_W + (width_nodes - 1) * GAP_X
    height = PAD * 2 + layers * NODE_H + (layers - 1) * GAP_Y

    def pos(v: Version) -> tuple[int, int]:
        return PAD + v.order * (NODE_W + GAP_X), PAD + v.layer * (NODE_H + GAP_Y)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" class="genealogy-graph" '
        f'aria-label="Lineage of {html.escape(genealogy.name)}: {len(versions)} versions">',
        "<defs>"
        '<marker id="gen-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="var(--color-faint)"/></marker></defs>',
    ]
    for parent_key, child_key in genealogy.edges:
        parent, child = versions[parent_key], versions[child_key]
        px, py = pos(parent)
        cx, cy = pos(child)
        x1, y1 = px + NODE_W // 2, py + NODE_H
        x2, y2 = cx + NODE_W // 2, cy
        if child.layer <= parent.layer:  # a revert back to earlier content
            x1, y1, x2, y2 = px + NODE_W, py + NODE_H // 2, cx + NODE_W, cy + NODE_H // 2
            bend = x1 + GAP_X
            d = f"M{x1},{y1} C{bend},{y1} {bend},{y2} {x2},{y2}"
            dash = ' stroke-dasharray="3 3"'
        else:
            mid = (y1 + y2) / 2
            d = f"M{x1},{y1} C{x1},{mid} {x2},{mid} {x2},{y2 - 2}"
            dash = ""
        parts.append(
            f'<path d="{d}" fill="none" stroke="var(--color-faint)" stroke-width="1.5"{dash} '
            'marker-end="url(#gen-arrow)"/>'
        )
    for v in versions.values():
        x, y = pos(v)
        stroke, text, dash = _colours(v)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        width_attr = "2.5" if v.current else "1.25"
        label = "no file here" if v.hash_only else v.writer_label
        body = (
            f'<rect x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}" rx="6" '
            f'fill="var(--color-surface)" stroke="{stroke}" stroke-width="{width_attr}"'
            f"{dash_attr}/>"
            f'<text x="{x + 10}" y="{y + 19}" fill="{text}" font-size="12" '
            f'font-family="var(--font-mono, monospace)">{html.escape(v.short)}</text>'
            f'<text x="{x + 10}" y="{y + 35}" fill="var(--color-muted)" font-size="11">'
            f"{html.escape(label)}{' · current' if v.current else ''}</text>"
        )
        title = f"<title>{html.escape(_node_title(v))}</title>"
        if v.hash_only:
            parts.append(f'<g class="gen-node">{title}{body}</g>')
        else:
            parts.append(
                f'<a href="#{anchor(v)}" class="gen-node" '
                f'aria-label="{html.escape(_node_title(v))}">{title}{body}</a>'
            )
    parts.append("</svg>")
    return "".join(parts)


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
