"""Tests for the SVG workflow diagram generator."""

from datetime import datetime, timezone

import pytest

from zebra.core.models import ProcessDefinition, RoutingDefinition, TaskDefinition
from zebra_agent.metrics import TaskExecution

from zebra_agent_web.diagram import (
    COLORS,
    NODE_HEIGHT,
    NODE_WIDTH,
    WorkflowDiagramGenerator,
    generate_workflow_svg,
)


@pytest.fixture
def simple_definition():
    """Create a simple linear workflow definition."""
    return ProcessDefinition(
        id="simple-workflow",
        name="Simple Workflow",
        version=1,
        first_task_id="start",
        tasks={
            "start": TaskDefinition(id="start", name="Start Task"),
            "process": TaskDefinition(id="process", name="Process Data"),
            "finish": TaskDefinition(id="finish", name="Finish Task"),
        },
        routings=[
            RoutingDefinition(id="r1", source_task_id="start", dest_task_id="process"),
            RoutingDefinition(id="r2", source_task_id="process", dest_task_id="finish"),
        ],
    )


@pytest.fixture
def parallel_definition():
    """Create a workflow with parallel branches."""
    return ProcessDefinition(
        id="parallel-workflow",
        name="Parallel Workflow",
        version=1,
        first_task_id="start",
        tasks={
            "start": TaskDefinition(id="start", name="Start"),
            "branch_a": TaskDefinition(id="branch_a", name="Branch A"),
            "branch_b": TaskDefinition(id="branch_b", name="Branch B"),
            "join": TaskDefinition(id="join", name="Join", synchronized=True),
        },
        routings=[
            RoutingDefinition(
                id="r1", source_task_id="start", dest_task_id="branch_a", parallel=True
            ),
            RoutingDefinition(
                id="r2", source_task_id="start", dest_task_id="branch_b", parallel=True
            ),
            RoutingDefinition(id="r3", source_task_id="branch_a", dest_task_id="join"),
            RoutingDefinition(id="r4", source_task_id="branch_b", dest_task_id="join"),
        ],
    )


@pytest.fixture
def sample_executions():
    """Create sample task executions."""
    base_time = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
    return [
        TaskExecution(
            id="exec-1",
            run_id="run-123",
            task_definition_id="start",
            task_name="Start Task",
            execution_order=1,
            state="complete",
            started_at=base_time,
            completed_at=datetime(2024, 1, 15, 10, 0, 30, tzinfo=timezone.utc),
            output={"status": "started"},
        ),
        TaskExecution(
            id="exec-2",
            run_id="run-123",
            task_definition_id="process",
            task_name="Process Data",
            execution_order=2,
            state="complete",
            started_at=datetime(2024, 1, 15, 10, 0, 30, tzinfo=timezone.utc),
            completed_at=datetime(2024, 1, 15, 10, 1, 0, tzinfo=timezone.utc),
            output={"processed": True},
        ),
        TaskExecution(
            id="exec-3",
            run_id="run-123",
            task_definition_id="finish",
            task_name="Finish Task",
            execution_order=3,
            state="complete",
            started_at=datetime(2024, 1, 15, 10, 1, 0, tzinfo=timezone.utc),
            completed_at=datetime(2024, 1, 15, 10, 1, 30, tzinfo=timezone.utc),
            output={"result": "success"},
        ),
    ]


class TestWorkflowDiagramGenerator:
    """Tests for WorkflowDiagramGenerator."""

    def test_init_without_executions(self, simple_definition):
        """Test initialization without executions."""
        generator = WorkflowDiagramGenerator(simple_definition)
        assert generator.definition == simple_definition
        assert generator.executions == []
        assert generator.execution_state == {}
        assert generator.execution_order == {}

    def test_init_with_executions(self, simple_definition, sample_executions):
        """Test initialization with executions."""
        generator = WorkflowDiagramGenerator(simple_definition, sample_executions)
        assert generator.executions == sample_executions
        assert generator.execution_state["start"] == "complete"
        assert generator.execution_state["process"] == "complete"
        assert generator.execution_state["finish"] == "complete"
        assert generator.execution_order["start"] == 1
        assert generator.execution_order["process"] == 2
        assert generator.execution_order["finish"] == 3

    def test_layout_linear_workflow(self, simple_definition):
        """Test layout calculation for linear workflow."""
        generator = WorkflowDiagramGenerator(simple_definition)
        generator._layout_tasks()

        # Should have 3 positions
        assert len(generator.positions) == 3

        # Tasks should be in different columns
        assert generator.positions["start"].column == 0
        assert generator.positions["process"].column == 1
        assert generator.positions["finish"].column == 2

        # All on same row for linear workflow
        assert generator.positions["start"].row == 0
        assert generator.positions["process"].row == 0
        assert generator.positions["finish"].row == 0

    def test_layout_parallel_workflow(self, parallel_definition):
        """Test layout calculation for parallel workflow."""
        generator = WorkflowDiagramGenerator(parallel_definition)
        generator._layout_tasks()

        # Should have 4 positions
        assert len(generator.positions) == 4

        # Start should be first column
        assert generator.positions["start"].column == 0

        # Parallel branches should be same column
        assert generator.positions["branch_a"].column == 1
        assert generator.positions["branch_b"].column == 1

        # Join should be last
        assert generator.positions["join"].column == 2

    def test_generate_svg_returns_string(self, simple_definition):
        """Test that generate_svg returns a string."""
        generator = WorkflowDiagramGenerator(simple_definition)
        svg = generator.generate_svg()

        assert isinstance(svg, str)
        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")

    def test_generate_svg_contains_all_tasks(self, simple_definition):
        """Test that SVG contains all task nodes."""
        generator = WorkflowDiagramGenerator(simple_definition)
        svg = generator.generate_svg()

        assert "Start Task" in svg
        assert "Process Data" in svg
        assert "Finish Task" in svg

    def test_generate_svg_contains_task_ids(self, simple_definition):
        """Test that SVG contains task IDs as data attributes."""
        generator = WorkflowDiagramGenerator(simple_definition)
        svg = generator.generate_svg()

        assert 'data-task-id="start"' in svg
        assert 'data-task-id="process"' in svg
        assert 'data-task-id="finish"' in svg

    def test_generate_svg_shows_execution_state(self, simple_definition, sample_executions):
        """Test that SVG shows execution state colors."""
        generator = WorkflowDiagramGenerator(simple_definition, sample_executions)
        svg = generator.generate_svg()

        # Complete tasks should have green color
        assert COLORS["complete"] in svg

    def test_generate_svg_shows_execution_order(self, simple_definition, sample_executions):
        """Test that SVG shows execution order numbers."""
        generator = WorkflowDiagramGenerator(simple_definition, sample_executions)
        svg = generator.generate_svg()

        # Should show order badges
        assert "#1" in svg
        assert "#2" in svg
        assert "#3" in svg

    def test_generate_svg_parallel_edges(self, parallel_definition):
        """Test that parallel edges are styled differently."""
        generator = WorkflowDiagramGenerator(parallel_definition)
        svg = generator.generate_svg()

        # Parallel edges should use dashed lines
        assert "stroke-dasharray" in svg

    def test_generate_svg_synchronized_task(self, parallel_definition):
        """Test that synchronized tasks are marked."""
        generator = WorkflowDiagramGenerator(parallel_definition)
        svg = generator.generate_svg()

        # Sync indicator
        assert "sync" in svg.lower()

    def test_generate_svg_with_failed_task(self, simple_definition):
        """Test SVG generation with a failed task."""
        failed_executions = [
            TaskExecution(
                id="exec-1",
                run_id="run-123",
                task_definition_id="start",
                task_name="Start Task",
                execution_order=1,
                state="complete",
                started_at=datetime.now(timezone.utc),
            ),
            TaskExecution(
                id="exec-2",
                run_id="run-123",
                task_definition_id="process",
                task_name="Process Data",
                execution_order=2,
                state="failed",
                started_at=datetime.now(timezone.utc),
                error="Task failed",
            ),
        ]

        generator = WorkflowDiagramGenerator(simple_definition, failed_executions)
        svg = generator.generate_svg()

        # Should have red color for failed task
        assert COLORS["failed"] in svg

    def test_generate_svg_dimensions(self, simple_definition):
        """Test that SVG has proper dimensions."""
        generator = WorkflowDiagramGenerator(simple_definition)
        svg = generator.generate_svg()

        # Should have viewBox
        assert "viewBox" in svg


class TestGenerateWorkflowSvg:
    """Tests for the generate_workflow_svg helper function."""

    def test_without_executions(self, simple_definition):
        """Test generating SVG without executions."""
        svg = generate_workflow_svg(simple_definition)
        assert isinstance(svg, str)
        assert "<svg" in svg

    def test_with_executions(self, simple_definition, sample_executions):
        """Test generating SVG with executions."""
        svg = generate_workflow_svg(simple_definition, sample_executions)
        assert isinstance(svg, str)
        assert "<svg" in svg
        assert COLORS["complete"] in svg

    def test_empty_definition(self):
        """Test generating SVG for definition with no tasks."""
        definition = ProcessDefinition(
            id="empty-workflow",
            name="Empty Workflow",
            version=1,
            first_task_id="",
            tasks={},
            routings=[],
        )
        svg = generate_workflow_svg(definition)
        assert isinstance(svg, str)
        assert "<svg" in svg


class TestDiagramStyles:
    """Tests for diagram styling."""

    def test_colors_defined(self):
        """Test that all necessary colors are defined."""
        required_colors = [
            "complete",
            "failed",
            "running",
            "skipped",
            "not_executed",
            "node_stroke",
            "node_fill",
            "text",
            "text_dim",
            "edge",
            "edge_parallel",
            "edge_executed",
        ]
        for color in required_colors:
            assert color in COLORS, f"Missing color: {color}"

    def test_node_dimensions(self):
        """Test that node dimensions are reasonable."""
        assert NODE_WIDTH > 0
        assert NODE_HEIGHT > 0
        assert NODE_WIDTH >= NODE_HEIGHT  # Nodes should be wider than tall


class TestEdgeRendering:
    """Tests for edge rendering."""

    def test_edges_rendered(self, simple_definition):
        """Test that edges are rendered."""
        generator = WorkflowDiagramGenerator(simple_definition)
        svg = generator.generate_svg()

        # Should have path elements for edges
        assert "<path" in svg
        # Should have arrow markers
        assert "marker-end" in svg

    def test_executed_edges_highlighted(self, simple_definition, sample_executions):
        """Test that executed edges are highlighted."""
        generator = WorkflowDiagramGenerator(simple_definition, sample_executions)
        svg = generator.generate_svg()

        # Executed edges should use the executed marker
        assert "arrowhead-executed" in svg
