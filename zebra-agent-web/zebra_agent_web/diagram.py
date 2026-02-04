"""SVG workflow diagram generator.

Generates SVG diagrams showing workflow structure and execution state.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebra.core.models import ProcessDefinition, RoutingDefinition, TaskDefinition
    from zebra_agent.metrics import TaskExecution


# Layout constants
NODE_WIDTH = 160
NODE_HEIGHT = 50
NODE_PADDING = 20
HORIZONTAL_GAP = 80
VERTICAL_GAP = 40
ARROW_HEAD_SIZE = 8
FONT_SIZE = 12
SMALL_FONT_SIZE = 10

# Colors (dark theme compatible)
COLORS = {
    "complete": "#22c55e",  # green-500
    "failed": "#ef4444",  # red-500
    "running": "#3b82f6",  # blue-500
    "skipped": "#6b7280",  # gray-500
    "not_executed": "#374151",  # gray-700
    "node_stroke": "#4b5563",  # gray-600
    "node_fill": "#1f2937",  # gray-800
    "text": "#f3f4f6",  # gray-100
    "text_dim": "#9ca3af",  # gray-400
    "edge": "#6b7280",  # gray-500
    "edge_parallel": "#8b5cf6",  # purple-500
    "edge_executed": "#22c55e",  # green-500
}


@dataclass
class NodePosition:
    """Position and layout info for a task node."""

    task_id: str
    x: int
    y: int
    column: int
    row: int


class WorkflowDiagramGenerator:
    """Generates SVG diagrams for workflow definitions with execution state."""

    def __init__(
        self,
        definition: ProcessDefinition,
        executions: list[TaskExecution] | None = None,
    ):
        """Initialize the diagram generator.

        Args:
            definition: The workflow definition to visualize
            executions: Optional list of task executions showing what was run
        """
        self.definition = definition
        self.executions = executions or []

        # Build execution state lookup
        self.execution_state: dict[str, str] = {}
        self.execution_order: dict[str, int] = {}
        for exec in self.executions:
            self.execution_state[exec.task_definition_id] = exec.state
            self.execution_order[exec.task_definition_id] = exec.execution_order

        # Will be populated during layout
        self.positions: dict[str, NodePosition] = {}
        self.width = 0
        self.height = 0

    def generate_svg(self) -> str:
        """Generate the complete SVG diagram.

        Returns:
            SVG string that can be embedded in HTML
        """
        # Calculate layout
        self._layout_tasks()

        # Start SVG
        padding = 20
        svg_width = self.width + padding * 2
        svg_height = self.height + padding * 2

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {svg_width} {svg_height}" '
            f'class="workflow-diagram" '
            f'style="max-width: 100%; height: auto;">',
            self._render_styles(),
            f'<g transform="translate({padding}, {padding})">',
        ]

        # Render edges first (behind nodes)
        svg_parts.append(self._render_edges())

        # Render nodes
        svg_parts.append(self._render_nodes())

        svg_parts.append("</g>")
        svg_parts.append("</svg>")

        return "\n".join(svg_parts)

    def _layout_tasks(self) -> None:
        """Calculate positions for all task nodes using topological sort."""
        tasks = self.definition.tasks
        routings = self.definition.routings

        if not tasks:
            return

        # Build adjacency lists
        outgoing: dict[str, list[str]] = {task_id: [] for task_id in tasks}
        incoming: dict[str, list[str]] = {task_id: [] for task_id in tasks}

        for routing in routings:
            if routing.source_task_id in outgoing:
                outgoing[routing.source_task_id].append(routing.dest_task_id)
            if routing.dest_task_id in incoming:
                incoming[routing.dest_task_id].append(routing.source_task_id)

        # Calculate column (x-position) using longest path from start
        columns: dict[str, int] = {}
        visited: set[str] = set()

        def calc_column(task_id: str) -> int:
            if task_id in columns:
                return columns[task_id]

            if task_id in visited:
                # Cycle detected, use current position
                return columns.get(task_id, 0)

            visited.add(task_id)

            # Column is 1 + max column of all predecessors
            predecessors = incoming.get(task_id, [])
            if not predecessors:
                col = 0
            else:
                col = max(calc_column(p) for p in predecessors) + 1

            columns[task_id] = col
            return col

        # Start from first task
        first_task_id = self.definition.first_task_id
        if first_task_id:
            calc_column(first_task_id)

        # Process all tasks
        for task_id in tasks:
            if task_id not in columns:
                calc_column(task_id)

        # Group tasks by column
        by_column: dict[int, list[str]] = {}
        for task_id, col in columns.items():
            by_column.setdefault(col, []).append(task_id)

        # Sort tasks in each column by:
        # 1. First task ID first
        # 2. Tasks with common predecessors together
        # 3. Execution order if available
        for col, task_ids in by_column.items():
            task_ids.sort(
                key=lambda t: (
                    0 if t == first_task_id else 1,
                    self.execution_order.get(t, 999),
                    t,
                )
            )

        # Calculate positions
        max_col = max(columns.values()) if columns else 0
        max_row = max(len(tasks_in_col) for tasks_in_col in by_column.values()) if by_column else 0

        for col, task_ids in by_column.items():
            for row, task_id in enumerate(task_ids):
                x = col * (NODE_WIDTH + HORIZONTAL_GAP)
                y = row * (NODE_HEIGHT + VERTICAL_GAP)

                self.positions[task_id] = NodePosition(
                    task_id=task_id,
                    x=x,
                    y=y,
                    column=col,
                    row=row,
                )

        # Calculate total dimensions
        self.width = (max_col + 1) * (NODE_WIDTH + HORIZONTAL_GAP) - HORIZONTAL_GAP + NODE_WIDTH
        self.height = max_row * (NODE_HEIGHT + VERTICAL_GAP) - VERTICAL_GAP + NODE_HEIGHT

        # Ensure minimum dimensions
        self.width = max(self.width, NODE_WIDTH * 2)
        self.height = max(self.height, NODE_HEIGHT)

    def _render_styles(self) -> str:
        """Render embedded CSS styles."""
        return f"""
        <style>
            .node {{
                cursor: pointer;
                transition: filter 0.2s ease;
            }}
            .node:hover {{
                filter: brightness(1.2);
            }}
            .node-rect {{
                rx: 8;
                ry: 8;
            }}
            .node-text {{
                font-family: ui-sans-serif, system-ui, sans-serif;
                font-size: {FONT_SIZE}px;
                fill: {COLORS["text"]};
                text-anchor: middle;
                dominant-baseline: middle;
                pointer-events: none;
            }}
            .node-order {{
                font-family: ui-monospace, monospace;
                font-size: {SMALL_FONT_SIZE}px;
                fill: {COLORS["text_dim"]};
            }}
            .status-icon {{
                pointer-events: none;
            }}
            .edge {{
                fill: none;
                stroke-width: 2;
            }}
            .edge-marker {{
                fill: {COLORS["edge"]};
            }}
            .edge-marker-executed {{
                fill: {COLORS["edge_executed"]};
            }}
        </style>
        """

    def _render_nodes(self) -> str:
        """Render all task nodes."""
        parts = ['<g class="nodes">']

        for task_id, pos in self.positions.items():
            task_def = self.definition.tasks.get(task_id)
            if not task_def:
                continue

            parts.append(self._render_node(task_def, pos))

        parts.append("</g>")
        return "\n".join(parts)

    def _render_node(self, task: TaskDefinition, pos: NodePosition) -> str:
        """Render a single task node."""
        state = self.execution_state.get(task.id, "not_executed")
        order = self.execution_order.get(task.id)

        # Determine colors based on state
        if state == "complete":
            stroke_color = COLORS["complete"]
            fill_color = COLORS["node_fill"]
        elif state == "failed":
            stroke_color = COLORS["failed"]
            fill_color = COLORS["node_fill"]
        elif state == "running":
            stroke_color = COLORS["running"]
            fill_color = COLORS["node_fill"]
        elif state == "skipped":
            stroke_color = COLORS["skipped"]
            fill_color = COLORS["node_fill"]
        else:
            stroke_color = COLORS["node_stroke"]
            fill_color = COLORS["node_fill"]

        # Calculate center positions
        cx = pos.x + NODE_WIDTH / 2
        cy = pos.y + NODE_HEIGHT / 2

        # Truncate name if too long
        name = task.name or task.id
        max_chars = NODE_WIDTH // 8  # Approximate chars that fit
        if len(name) > max_chars:
            name = name[: max_chars - 2] + ".."

        # Build node SVG
        parts = [
            f'<g class="node" data-task-id="{html.escape(task.id)}" '
            f"onclick=\"selectTask('{html.escape(task.id)}')\" "
            f'role="button" tabindex="0">',
            # Background rectangle
            f'<rect class="node-rect" '
            f'x="{pos.x}" y="{pos.y}" '
            f'width="{NODE_WIDTH}" height="{NODE_HEIGHT}" '
            f'fill="{fill_color}" stroke="{stroke_color}" stroke-width="2"/>',
            # Task name
            f'<text class="node-text" x="{cx}" y="{cy}">{html.escape(name)}</text>',
        ]

        # Status icon (top-right corner)
        icon_x = pos.x + NODE_WIDTH - 20
        icon_y = pos.y + 10
        parts.append(self._render_status_icon(state, icon_x, icon_y))

        # Execution order badge (top-left corner)
        if order is not None:
            parts.append(
                f'<text class="node-order" x="{pos.x + 8}" y="{pos.y + 14}">#{order}</text>'
            )

        # Synchronized indicator (bottom-center)
        if task.synchronized:
            sync_y = pos.y + NODE_HEIGHT - 8
            parts.append(
                f'<text class="node-order" x="{cx}" y="{sync_y}" text-anchor="middle">sync</text>'
            )

        parts.append("</g>")
        return "\n".join(parts)

    def _render_status_icon(self, state: str, x: float, y: float) -> str:
        """Render a status icon for the given state."""
        size = 12

        if state == "complete":
            # Checkmark
            return (
                f'<g class="status-icon" transform="translate({x}, {y})">'
                f'<circle cx="{size / 2}" cy="{size / 2}" r="{size / 2}" '
                f'fill="{COLORS["complete"]}"/>'
                f'<path d="M{size * 0.25} {size * 0.5} L{size * 0.45} {size * 0.7} '
                f'L{size * 0.75} {size * 0.3}" '
                f'stroke="white" stroke-width="1.5" fill="none"/>'
                f"</g>"
            )
        elif state == "failed":
            # X mark
            return (
                f'<g class="status-icon" transform="translate({x}, {y})">'
                f'<circle cx="{size / 2}" cy="{size / 2}" r="{size / 2}" '
                f'fill="{COLORS["failed"]}"/>'
                f'<path d="M{size * 0.3} {size * 0.3} L{size * 0.7} {size * 0.7} '
                f'M{size * 0.7} {size * 0.3} L{size * 0.3} {size * 0.7}" '
                f'stroke="white" stroke-width="1.5"/>'
                f"</g>"
            )
        elif state == "running":
            # Spinning indicator
            return (
                f'<g class="status-icon" transform="translate({x}, {y})">'
                f'<circle cx="{size / 2}" cy="{size / 2}" r="{size / 2}" '
                f'fill="{COLORS["running"]}"/>'
                f'<circle cx="{size / 2}" cy="{size / 2}" r="{size * 0.3}" '
                f'fill="white"/>'
                f"</g>"
            )
        else:
            # Empty circle for not executed
            return (
                f'<g class="status-icon" transform="translate({x}, {y})">'
                f'<circle cx="{size / 2}" cy="{size / 2}" r="{size / 2 - 1}" '
                f'fill="none" stroke="{COLORS["node_stroke"]}" stroke-width="1"/>'
                f"</g>"
            )

    def _render_edges(self) -> str:
        """Render all routing edges."""
        parts = ['<g class="edges">']

        # Add arrow marker definitions
        parts.append(self._render_markers())

        for routing in self.definition.routings:
            parts.append(self._render_edge(routing))

        parts.append("</g>")
        return "\n".join(parts)

    def _render_markers(self) -> str:
        """Render SVG marker definitions for arrowheads."""
        return f"""
        <defs>
            <marker id="arrowhead" markerWidth="{ARROW_HEAD_SIZE}" 
                    markerHeight="{ARROW_HEAD_SIZE}" 
                    refX="{ARROW_HEAD_SIZE}" refY="{ARROW_HEAD_SIZE / 2}" 
                    orient="auto">
                <polygon points="0 0, {ARROW_HEAD_SIZE} {ARROW_HEAD_SIZE / 2}, 0 {ARROW_HEAD_SIZE}" 
                         class="edge-marker"/>
            </marker>
            <marker id="arrowhead-executed" markerWidth="{ARROW_HEAD_SIZE}" 
                    markerHeight="{ARROW_HEAD_SIZE}" 
                    refX="{ARROW_HEAD_SIZE}" refY="{ARROW_HEAD_SIZE / 2}" 
                    orient="auto">
                <polygon points="0 0, {ARROW_HEAD_SIZE} {ARROW_HEAD_SIZE / 2}, 0 {ARROW_HEAD_SIZE}" 
                         class="edge-marker-executed"/>
            </marker>
            <marker id="arrowhead-parallel" markerWidth="{ARROW_HEAD_SIZE}" 
                    markerHeight="{ARROW_HEAD_SIZE}" 
                    refX="{ARROW_HEAD_SIZE}" refY="{ARROW_HEAD_SIZE / 2}" 
                    orient="auto">
                <polygon points="0 0, {ARROW_HEAD_SIZE} {ARROW_HEAD_SIZE / 2}, 0 {ARROW_HEAD_SIZE}" 
                         fill="{COLORS["edge_parallel"]}"/>
            </marker>
        </defs>
        """

    def _render_edge(self, routing: RoutingDefinition) -> str:
        """Render a single routing edge."""
        source_pos = self.positions.get(routing.source_task_id)
        dest_pos = self.positions.get(routing.dest_task_id)

        if not source_pos or not dest_pos:
            return ""

        # Check if this edge was executed
        source_executed = routing.source_task_id in self.execution_state
        dest_executed = routing.dest_task_id in self.execution_state
        edge_executed = source_executed and dest_executed

        # Determine edge style
        if edge_executed:
            stroke_color = COLORS["edge_executed"]
            marker = "url(#arrowhead-executed)"
            stroke_width = 2.5
        elif routing.parallel:
            stroke_color = COLORS["edge_parallel"]
            marker = "url(#arrowhead-parallel)"
            stroke_width = 2
        else:
            stroke_color = COLORS["edge"]
            marker = "url(#arrowhead)"
            stroke_width = 2

        # Dash pattern for parallel edges
        dash = 'stroke-dasharray="5,3"' if routing.parallel and not edge_executed else ""

        # Calculate edge path
        # Start from right edge of source, end at left edge of dest
        x1 = source_pos.x + NODE_WIDTH
        y1 = source_pos.y + NODE_HEIGHT / 2
        x2 = dest_pos.x - ARROW_HEAD_SIZE  # Leave room for arrow
        y2 = dest_pos.y + NODE_HEIGHT / 2

        # Use curved path if nodes are on different rows
        if source_pos.row != dest_pos.row:
            # Control points for curve
            ctrl_x = (x1 + x2) / 2
            path = f"M {x1} {y1} C {ctrl_x} {y1}, {ctrl_x} {y2}, {x2} {y2}"
        else:
            # Straight line
            path = f"M {x1} {y1} L {x2} {y2}"

        return (
            f'<path class="edge" d="{path}" '
            f'stroke="{stroke_color}" stroke-width="{stroke_width}" '
            f'{dash} marker-end="{marker}"/>'
        )


def generate_workflow_svg(
    definition: ProcessDefinition,
    executions: list[TaskExecution] | None = None,
) -> str:
    """Generate an SVG diagram for a workflow.

    Args:
        definition: The workflow definition
        executions: Optional list of task executions

    Returns:
        SVG string
    """
    generator = WorkflowDiagramGenerator(definition, executions)
    return generator.generate_svg()
