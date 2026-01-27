"""Tests for the CLI module."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zebra_agent.library import WorkflowLibrary
from zebra_agent.memory import LongTermTheme, MemoryEntry, ShortTermSummary
from zebra_agent.metrics import WorkflowRun, WorkflowStats

from zebra_agent_cli.main import (
    cmd_help,
    cmd_list,
    cmd_memory,
    cmd_stats,
    print_banner,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def library_path(temp_dir):
    """Create a library directory."""
    lib_path = temp_dir / "workflows"
    lib_path.mkdir()
    return lib_path


@pytest.fixture
def library(library_path, metrics):
    """Create a WorkflowLibrary instance."""
    return WorkflowLibrary(library_path, metrics)


class TestPrintBanner:
    """Tests for print_banner function."""

    def test_print_banner(self, capsys):
        """Test that banner is printed."""
        print_banner()
        captured = capsys.readouterr()
        assert "Zebra Agent" in captured.out
        assert "/list" in captured.out
        assert "/stats" in captured.out
        assert "/memory" in captured.out
        assert "/help" in captured.out
        assert "/quit" in captured.out


class TestCmdHelp:
    """Tests for cmd_help function."""

    def test_cmd_help(self, capsys):
        """Test that help is printed."""
        cmd_help()
        captured = capsys.readouterr()
        assert "/list" in captured.out
        assert "/stats" in captured.out
        assert "/memory" in captured.out
        assert "/quit" in captured.out
        assert "/exit" in captured.out
        assert "Examples:" in captured.out


class TestCmdList:
    """Tests for cmd_list function."""

    async def test_cmd_list_empty(self, library, capsys):
        """Test listing when no workflows exist."""
        await cmd_list(library)
        captured = capsys.readouterr()
        assert "No workflows available" in captured.out

    async def test_cmd_list_with_workflows(self, library, capsys):
        """Test listing with workflows."""
        yaml_content = """name: "Test Workflow"
description: "A test workflow"
tags: ["test", "sample"]
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "{{goal}}"
      output_key: result
routings: []
"""
        (library.library_path / "test.yaml").write_text(yaml_content)

        await cmd_list(library)
        captured = capsys.readouterr()
        assert "Test Workflow" in captured.out
        assert "A test workflow" in captured.out
        assert "test, sample" in captured.out


class TestCmdStats:
    """Tests for cmd_stats function."""

    async def test_cmd_stats_empty(self, metrics, capsys):
        """Test stats when no runs exist."""
        await cmd_stats(metrics)
        captured = capsys.readouterr()
        assert "Workflow Statistics" in captured.out
        assert "No workflow runs recorded" in captured.out

    async def test_cmd_stats_with_data(self, metrics, capsys):
        """Test stats with runs."""
        # Record some runs
        for i in range(3):
            run = WorkflowRun.create("TestWorkflow", f"Goal {i}")
            run.success = True
            run.user_rating = 4
            await metrics.record_run(run)

        await cmd_stats(metrics)
        captured = capsys.readouterr()
        assert "TestWorkflow" in captured.out
        assert "Runs: 3" in captured.out
        assert "Success: 100%" in captured.out

    async def test_cmd_stats_with_recent_runs(self, metrics, capsys):
        """Test stats shows recent runs."""
        run = WorkflowRun.create(
            "TestWorkflow", "Test goal that is quite long and should be truncated"
        )
        run.success = True
        run.user_rating = 5
        await metrics.record_run(run)

        await cmd_stats(metrics)
        captured = capsys.readouterr()
        assert "Recent Runs" in captured.out
        assert "TestWorkflow" in captured.out


class TestCmdMemory:
    """Tests for cmd_memory function."""

    async def test_cmd_memory_empty(self, memory, capsys):
        """Test memory status when empty."""
        await cmd_memory(memory)
        captured = capsys.readouterr()
        assert "Memory Status" in captured.out
        assert "SHORT-TERM MEMORY" in captured.out
        assert "LONG-TERM MEMORY" in captured.out
        assert "No memory entries yet" in captured.out

    async def test_cmd_memory_with_entries(self, memory, capsys):
        """Test memory status with entries."""
        entry = MemoryEntry(
            id="test-1",
            timestamp=datetime.now(),
            goal="Test goal",
            workflow_used="TestWorkflow",
            result_summary="Test result",
            tokens=100,
        )
        await memory.add_entry(entry)

        await cmd_memory(memory)
        captured = capsys.readouterr()
        assert "Recent interactions" in captured.out
        assert "Test goal" in captured.out
        assert "TestWorkflow" in captured.out

    async def test_cmd_memory_with_summaries(self, memory, capsys):
        """Test memory status with summaries."""
        summary = ShortTermSummary(
            id="sum-1",
            created_at=datetime.now(),
            summary="Test summary content",
            tokens=50,
            entry_count=5,
        )
        await memory.add_short_term_summary(summary)

        await cmd_memory(memory)
        captured = capsys.readouterr()
        assert "Recent summaries" in captured.out
        assert "5 entries summarized" in captured.out

    async def test_cmd_memory_with_themes(self, memory, capsys):
        """Test memory status with themes."""
        theme = LongTermTheme(
            id="theme-1",
            created_at=datetime.now(),
            theme="Test theme content",
            tokens=30,
            short_term_refs=["sum-1", "sum-2"],
        )
        await memory.add_long_term_theme(theme)

        await cmd_memory(memory)
        captured = capsys.readouterr()
        assert "Themes (long-term)" in captured.out
        assert "refs: 2 summaries" in captured.out

    async def test_cmd_memory_token_usage(self, memory, capsys):
        """Test memory shows token usage."""
        entry = MemoryEntry(
            id="test-1",
            timestamp=datetime.now(),
            goal="Test",
            workflow_used="Test",
            result_summary="Test",
            tokens=500,  # 50% of 1000 max
        )
        await memory.add_entry(entry)

        await cmd_memory(memory)
        captured = capsys.readouterr()
        assert "500" in captured.out
        assert "1,000" in captured.out
        assert "50.0%" in captured.out


class TestCmdListWithMetrics:
    """Tests for cmd_list with metrics integration."""

    async def test_cmd_list_shows_success_rate(self, library, metrics, capsys):
        """Test that list shows success rate from metrics."""
        yaml_content = """name: "Test Workflow"
description: "Test"
tags: []
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "{{goal}}"
      output_key: result
routings: []
"""
        (library.library_path / "test.yaml").write_text(yaml_content)

        # Record some runs
        for i in range(10):
            run = WorkflowRun.create("Test Workflow", f"Goal {i}")
            run.success = i < 8  # 80% success
            await metrics.record_run(run)

        await cmd_list(library)
        captured = capsys.readouterr()
        assert "80%" in captured.out
        assert "Uses: 10" in captured.out


class TestAsyncMain:
    """Tests for the async_main function."""

    async def test_async_main_quit_command(self, temp_dir, capsys):
        """Test quitting with /quit command."""
        from zebra_agent_cli.main import async_main

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("builtins.input", side_effect=["/quit"]),
        ):
            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "Goodbye" in captured.out

    async def test_async_main_exit_command(self, temp_dir, capsys):
        """Test quitting with /exit command."""
        from zebra_agent_cli.main import async_main

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("builtins.input", side_effect=["/exit"]),
        ):
            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "Goodbye" in captured.out

    async def test_async_main_q_command(self, temp_dir, capsys):
        """Test quitting with /q command."""
        from zebra_agent_cli.main import async_main

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("builtins.input", side_effect=["/q"]),
        ):
            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "Goodbye" in captured.out

    async def test_async_main_help_command(self, temp_dir, capsys):
        """Test /help command."""
        from zebra_agent_cli.main import async_main

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("builtins.input", side_effect=["/help", "/quit"]),
        ):
            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "/list" in captured.out
        assert "/stats" in captured.out

    async def test_async_main_list_command(self, temp_dir, capsys):
        """Test /list command."""
        from zebra_agent_cli.main import async_main

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        mock_metrics = MagicMock()
        # list_workflows calls get_stats which is async
        mock_metrics.get_stats = AsyncMock(return_value=WorkflowStats("test"))

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore", return_value=mock_metrics),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("builtins.input", side_effect=["/list", "/quit"]),
        ):
            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "No workflows available" in captured.out

    async def test_async_main_stats_command(self, temp_dir, capsys):
        """Test /stats command."""
        from zebra_agent_cli.main import async_main

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        mock_metrics = MagicMock()
        mock_metrics.get_all_stats = AsyncMock(
            return_value=[
                WorkflowStats(
                    workflow_name="TestWorkflow", total_runs=10, successful_runs=8, avg_rating=4.5
                )
            ]
        )
        mock_metrics.get_recent_runs = AsyncMock(return_value=[])

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore", return_value=mock_metrics),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("builtins.input", side_effect=["/stats", "/quit"]),
        ):
            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "Workflow Statistics" in captured.out
        assert "TestWorkflow" in captured.out

    async def test_async_main_memory_command(self, temp_dir, capsys):
        """Test /memory command."""
        from zebra_agent_cli.main import async_main

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        mock_memory = MagicMock()
        mock_memory.short_term_max_tokens = 1000
        mock_memory.long_term_max_tokens = 2000
        mock_memory.compact_threshold = 0.9
        mock_memory.get_stats = AsyncMock(
            return_value={
                "short_term": {
                    "entry_count": 0,
                    "entry_tokens": 0,
                    "summary_count": 0,
                    "summary_tokens": 0,
                },
                "long_term": {"theme_count": 0, "theme_tokens": 0},
            }
        )
        mock_memory.get_short_term_entries = AsyncMock(return_value=[])
        mock_memory.get_short_term_summaries = AsyncMock(return_value=[])
        mock_memory.get_long_term_themes = AsyncMock(return_value=[])

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory", return_value=mock_memory),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("builtins.input", side_effect=["/memory", "/quit"]),
        ):
            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "Memory Status" in captured.out

    async def test_async_main_unknown_command(self, temp_dir, capsys):
        """Test unknown command."""
        from zebra_agent_cli.main import async_main

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("builtins.input", side_effect=["/unknown", "/quit"]),
        ):
            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "Unknown command" in captured.out
        assert "/help" in captured.out

    async def test_async_main_empty_input(self, temp_dir, capsys):
        """Test empty input is skipped."""
        from zebra_agent_cli.main import async_main

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("builtins.input", side_effect=["", "   ", "/quit"]),
        ):
            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        # Should just quit without processing empty input
        assert "Goodbye" in captured.out

    async def test_async_main_eof_error(self, temp_dir, capsys):
        """Test EOFError handling."""
        from zebra_agent_cli.main import async_main

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("builtins.input", side_effect=EOFError),
        ):
            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "Goodbye" in captured.out

    async def test_async_main_keyboard_interrupt(self, temp_dir, capsys):
        """Test KeyboardInterrupt handling."""
        from zebra_agent_cli.main import async_main

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("builtins.input", side_effect=[KeyboardInterrupt, "/quit"]),
        ):
            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "/quit to exit" in captured.out

    async def test_async_main_copies_builtin_workflows(self, temp_dir, capsys):
        """Test that builtin workflows are copied."""
        from zebra_agent_cli.main import async_main

        builtin_path = temp_dir / "builtin"
        builtin_path.mkdir()
        (builtin_path / "test.yaml").write_text("""name: "Builtin Workflow"
description: "A builtin workflow"
tags: []
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "test"
      output_key: result
routings: []
""")

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", builtin_path),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("builtins.input", side_effect=["/quit"]),
        ):
            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "Copied 1 built-in workflows" in captured.out

    async def test_async_main_process_goal_success(self, temp_dir, capsys):
        """Test processing a goal successfully."""
        from zebra_agent.loop import AgentResult

        from zebra_agent_cli.main import async_main

        mock_result = AgentResult(
            run_id="test-id",
            workflow_name="Test Workflow",
            goal="Test goal",
            output="Test output result",
            success=True,
            tokens_used=50,
            created_new_workflow=False,
        )

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("zebra_agent_cli.main.AgentLoop") as mock_agent_class,
            patch("builtins.input", side_effect=["What is 2+2?", "", "/quit"]),
        ):
            mock_agent = MagicMock()
            mock_agent.process_goal = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "Processing" in captured.out
        assert "Test Workflow" in captured.out
        assert "Test output result" in captured.out
        assert "Tokens used: 50" in captured.out

    async def test_async_main_process_goal_new_workflow(self, temp_dir, capsys):
        """Test processing a goal that creates a new workflow."""
        from zebra_agent.loop import AgentResult

        from zebra_agent_cli.main import async_main

        mock_result = AgentResult(
            run_id="test-id",
            workflow_name="New Workflow",
            goal="Test goal",
            output="Output",
            success=True,
            tokens_used=100,
            created_new_workflow=True,
        )

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("zebra_agent_cli.main.AgentLoop") as mock_agent_class,
            patch("builtins.input", side_effect=["Create something new", "", "/quit"]),
        ):
            mock_agent = MagicMock()
            mock_agent.process_goal = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "Created new workflow: New Workflow" in captured.out

    async def test_async_main_process_goal_dict_output(self, temp_dir, capsys):
        """Test processing a goal with dict output."""
        from zebra_agent.loop import AgentResult

        from zebra_agent_cli.main import async_main

        mock_result = AgentResult(
            run_id="test-id",
            workflow_name="Test Workflow",
            goal="Test goal",
            output={"answer": "The answer is 42", "confidence": "high"},
            success=True,
            tokens_used=75,
        )

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("zebra_agent_cli.main.AgentLoop") as mock_agent_class,
            patch("builtins.input", side_effect=["What is the meaning of life?", "", "/quit"]),
        ):
            mock_agent = MagicMock()
            mock_agent.process_goal = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "The answer is 42" in captured.out
        assert "high" in captured.out

    async def test_async_main_process_goal_with_rating(self, temp_dir, capsys):
        """Test processing a goal and giving a rating."""
        from zebra_agent.loop import AgentResult

        from zebra_agent_cli.main import async_main

        mock_result = AgentResult(
            run_id="test-id",
            workflow_name="Test Workflow",
            goal="Test goal",
            output="Output",
            success=True,
            tokens_used=50,
        )

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("zebra_agent_cli.main.AgentLoop") as mock_agent_class,
            patch("builtins.input", side_effect=["Test", "5", "/quit"]),
        ):
            mock_agent = MagicMock()
            mock_agent.process_goal = AsyncMock(return_value=mock_result)
            mock_agent.record_rating = AsyncMock()
            mock_agent_class.return_value = mock_agent

            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "Thanks for the feedback" in captured.out
        mock_agent.record_rating.assert_called_once_with("test-id", 5)

    async def test_async_main_process_goal_invalid_rating(self, temp_dir, capsys):
        """Test processing a goal with invalid rating."""
        from zebra_agent.loop import AgentResult

        from zebra_agent_cli.main import async_main

        mock_result = AgentResult(
            run_id="test-id",
            workflow_name="Test Workflow",
            goal="Test goal",
            output="Output",
            success=True,
            tokens_used=50,
        )

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("zebra_agent_cli.main.AgentLoop") as mock_agent_class,
            patch("builtins.input", side_effect=["Test", "10", "/quit"]),
        ):
            mock_agent = MagicMock()
            mock_agent.process_goal = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "Rating must be between 1 and 5" in captured.out

    async def test_async_main_process_goal_skip_rating(self, temp_dir, capsys):
        """Test skipping rating with empty input."""
        from zebra_agent.loop import AgentResult

        from zebra_agent_cli.main import async_main

        mock_result = AgentResult(
            run_id="test-id",
            workflow_name="Test Workflow",
            goal="Test goal",
            output="Output",
            success=True,
            tokens_used=50,
        )

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("zebra_agent_cli.main.AgentLoop") as mock_agent_class,
            patch("builtins.input", side_effect=["Test", "", "/quit"]),
        ):
            mock_agent = MagicMock()
            mock_agent.process_goal = AsyncMock(return_value=mock_result)
            mock_agent.record_rating = AsyncMock()
            mock_agent_class.return_value = mock_agent

            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        # Should not call record_rating
        mock_agent.record_rating.assert_not_called()

    async def test_async_main_process_goal_failure(self, temp_dir, capsys):
        """Test processing a goal that fails."""
        from zebra_agent.loop import AgentResult

        from zebra_agent_cli.main import async_main

        mock_result = AgentResult(
            run_id="test-id",
            workflow_name="Test Workflow",
            goal="Test goal",
            output=None,
            success=False,
            error="Something went wrong",
        )

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("zebra_agent_cli.main.AgentLoop") as mock_agent_class,
            patch("builtins.input", side_effect=["Test goal", "/quit"]),
        ):
            mock_agent = MagicMock()
            mock_agent.process_goal = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "Error: Something went wrong" in captured.out

    async def test_async_main_process_goal_exception(self, temp_dir, capsys):
        """Test handling exception during goal processing."""
        from zebra_agent_cli.main import async_main

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("zebra_agent_cli.main.AgentLoop") as mock_agent_class,
            patch("builtins.input", side_effect=["Test", "/quit"]),
        ):
            mock_agent = MagicMock()
            mock_agent.process_goal = AsyncMock(side_effect=RuntimeError("Unexpected error"))
            mock_agent_class.return_value = mock_agent

            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        assert "Error: Unexpected error" in captured.out

    async def test_async_main_rating_eof_error(self, temp_dir, capsys):
        """Test EOFError during rating input."""
        from zebra_agent.loop import AgentResult

        from zebra_agent_cli.main import async_main

        mock_result = AgentResult(
            run_id="test-id",
            workflow_name="Test Workflow",
            goal="Test goal",
            output="Output",
            success=True,
            tokens_used=50,
        )

        input_responses = iter(["Test", EOFError, "/quit"])

        def mock_input(prompt=""):
            resp = next(input_responses)
            if isinstance(resp, type) and issubclass(resp, Exception):
                raise resp()
            return resp

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("zebra_agent_cli.main.AgentLoop") as mock_agent_class,
            patch("builtins.input", side_effect=mock_input),
        ):
            mock_agent = MagicMock()
            mock_agent.process_goal = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        # Should handle EOFError gracefully and continue
        captured = capsys.readouterr()
        assert "Goodbye" in captured.out

    async def test_async_main_no_tokens_used(self, temp_dir, capsys):
        """Test output when no tokens are used."""
        from zebra_agent.loop import AgentResult

        from zebra_agent_cli.main import async_main

        mock_result = AgentResult(
            run_id="test-id",
            workflow_name="Test Workflow",
            goal="Test goal",
            output="Output",
            success=True,
            tokens_used=0,
        )

        mock_store = MagicMock()
        mock_store.initialize = AsyncMock()

        with (
            patch("zebra_agent_cli.main.DEFAULT_DATA_DIR", temp_dir),
            patch("zebra_agent_cli.main.DEFAULT_WORKFLOWS_DIR", temp_dir / "workflows"),
            patch("zebra_agent_cli.main.BUILTIN_WORKFLOWS", temp_dir / "builtin"),
            patch("zebra_agent_cli.main.MetricsStore"),
            patch("zebra_agent_cli.main.AgentMemory"),
            patch("zebra_agent_cli.main.PostgreSQLStore", return_value=mock_store),
            patch("zebra_agent_cli.main.WorkflowEngine"),
            patch("zebra_agent_cli.main.AgentLoop") as mock_agent_class,
            patch("builtins.input", side_effect=["Test", "", "/quit"]),
        ):
            mock_agent = MagicMock()
            mock_agent.process_goal = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            (temp_dir / "workflows").mkdir(exist_ok=True)
            await async_main()

        captured = capsys.readouterr()
        # Should not show "Tokens used" when 0
        assert "Tokens used" not in captured.out


class TestRunFunction:
    """Tests for the run entry point function."""

    def test_run_normal_exit(self, temp_dir):
        """Test normal run and exit."""
        from zebra_agent_cli.main import run

        with patch("zebra_agent_cli.main.asyncio.run") as mock_asyncio_run:
            mock_asyncio_run.return_value = None
            run()
            mock_asyncio_run.assert_called_once()

    def test_run_keyboard_interrupt(self, temp_dir, capsys):
        """Test run with KeyboardInterrupt."""
        from zebra_agent_cli.main import run

        with (
            patch("zebra_agent_cli.main.asyncio.run", side_effect=KeyboardInterrupt),
            pytest.raises(SystemExit) as exc_info,
        ):
            run()

        captured = capsys.readouterr()
        assert "Goodbye" in captured.out
        assert exc_info.value.code == 0
