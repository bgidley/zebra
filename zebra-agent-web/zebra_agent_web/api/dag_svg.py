"""Inline SVG for a layered DAG: the renderer shared by the genealogy pages (#238, #247).

Nodes are placed by ``(layer, order)`` (``zebra_agent.genealogy.layer_dag``), parents above
children. Colours are theme tokens through CSS variables, so a graph follows light and dark like
the rest of the page (``specs/web-ui-design.md``). A node with an ``href`` is a focusable link;
every node has a ``<title>`` naming it for screen readers. No JavaScript.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

NODE_W = 132
NODE_H = 46
GAP_X = 20
GAP_Y = 34
PAD = 8


@dataclass(frozen=True)
class DagNode:
    """One box: a mono first line, a muted second line, its look and an optional link."""

    key: str
    layer: int
    order: int
    line1: str
    line2: str
    title: str
    href: str | None = None
    stroke: str = "var(--color-muted)"
    text: str = "var(--color-ink)"
    dash: str = ""
    strong: bool = False


@dataclass(frozen=True)
class DagEdge:
    """``parent`` → ``child``; ``dashed`` for a weaker or negative link."""

    parent: str
    child: str
    dashed: bool = False


def dag_svg(nodes: list[DagNode], edges: list[DagEdge], label: str, *, marker: str) -> str:
    """The graph as an inline SVG; ``""`` when there are no nodes.

    *marker* is the arrowhead's element id, unique per graph on the page.
    """
    if not nodes:
        return ""
    by_key = {n.key: n for n in nodes}
    width_nodes = max(n.order for n in nodes) + 1
    layers = max(n.layer for n in nodes) + 1
    width = PAD * 2 + width_nodes * NODE_W + (width_nodes - 1) * GAP_X
    height = PAD * 2 + layers * NODE_H + (layers - 1) * GAP_Y

    def pos(n: DagNode) -> tuple[int, int]:
        return PAD + n.order * (NODE_W + GAP_X), PAD + n.layer * (NODE_H + GAP_Y)

    marker = html.escape(marker)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" class="genealogy-graph" '
        f'aria-label="{html.escape(label)}">',
        "<defs>"
        f'<marker id="{marker}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="var(--color-faint)"/></marker></defs>',
    ]
    for edge in edges:
        parent, child = by_key.get(edge.parent), by_key.get(edge.child)
        if parent is None or child is None:
            continue
        px, py = pos(parent)
        cx, cy = pos(child)
        x1, y1 = px + NODE_W // 2, py + NODE_H
        x2, y2 = cx + NODE_W // 2, cy
        dashed = edge.dashed
        if child.layer <= parent.layer:  # a cycle back to an earlier node
            x1, y1, x2, y2 = px + NODE_W, py + NODE_H // 2, cx + NODE_W, cy + NODE_H // 2
            bend = x1 + GAP_X
            d = f"M{x1},{y1} C{bend},{y1} {bend},{y2} {x2},{y2}"
            dashed = True
        else:
            mid = (y1 + y2) / 2
            d = f"M{x1},{y1} C{x1},{mid} {x2},{mid} {x2},{y2 - 2}"
        dash = ' stroke-dasharray="3 3"' if dashed else ""
        parts.append(
            f'<path d="{d}" fill="none" stroke="var(--color-faint)" stroke-width="1.5"{dash} '
            f'marker-end="url(#{marker})"/>'
        )
    for n in nodes:
        x, y = pos(n)
        dash_attr = f' stroke-dasharray="{n.dash}"' if n.dash else ""
        body = (
            f'<rect x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}" rx="6" '
            f'fill="var(--color-surface)" stroke="{n.stroke}" '
            f'stroke-width="{"2.5" if n.strong else "1.25"}"{dash_attr}/>'
            f'<text x="{x + 10}" y="{y + 19}" fill="{n.text}" font-size="12" '
            f'font-family="var(--font-mono, monospace)">{html.escape(n.line1)}</text>'
            f'<text x="{x + 10}" y="{y + 35}" fill="var(--color-muted)" font-size="11">'
            f"{html.escape(n.line2)}</text>"
        )
        title = f"<title>{html.escape(n.title)}</title>"
        if n.href is None:
            parts.append(f'<g class="gen-node">{title}{body}</g>')
        else:
            parts.append(
                f'<a href="{html.escape(n.href)}" class="gen-node" '
                f'aria-label="{html.escape(n.title)}">{title}{body}</a>'
            )
    parts.append("</svg>")
    return "".join(parts)
