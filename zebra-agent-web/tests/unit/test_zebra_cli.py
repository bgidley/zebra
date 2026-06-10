"""Tests for the zebra terminal client (F34 / REQ-UI-003).

Covers the Oracle backend guard, the goal handler (run + queue modes), and
the goals listing handler. All external machinery is mocked; the Oracle
integration path is covered separately in test_agent_loop_integration.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Backend guard
# ---------------------------------------------------------------------------


class TestCheckBackend:
    def test_sqlite_without_flag_exits(self, capsys):
        from zebra_agent_web.cli import _check_backend

        connection = MagicMock()
        connection.vendor = "sqlite"
        with patch("zebra_agent_web.cli.sys.exit", side_effect=SystemExit(1)) as mock_exit:
            with patch("django.db.connections", {"default": connection}):
                with pytest.raises(SystemExit):
                    _check_backend(allow_sqlite=False)
        mock_exit.assert_called_once_with(1)
        err = capsys.readouterr().err
        assert "sqlite" in err
        assert "ORACLE_DSN" in err

    def test_sqlite_with_flag_proceeds(self):
        from zebra_agent_web.cli import _check_backend

        connection = MagicMock()
        connection.vendor = "sqlite"
        with patch("django.db.connections", {"default": connection}):
            _check_backend(allow_sqlite=True)  # must not raise

    def test_oracle_proceeds(self):
        from zebra_agent_web.cli import _check_backend

        connection = MagicMock()
        connection.vendor = "oracle"
        with patch("django.db.connections", {"default": connection}):
            _check_backend(allow_sqlite=False)  # must not raise


# ---------------------------------------------------------------------------
# goal handler
# ---------------------------------------------------------------------------


class TestGoalHandler:
    async def test_queue_mode_calls_queue_goal(self, capsys):
        from zebra_agent_web.cli import _goal_async

        process = MagicMock()
        process.id = "proc-abc123"
        with patch(
            "zebra_agent_web.api.goals.queue_goal", new=AsyncMock(return_value=process)
        ) as mock_queue:
            code = await _goal_async("Do a thing", model="haiku", queue=True, priority=2)

        assert code == 0
        mock_queue.assert_awaited_once_with("Do a thing", model="haiku", priority=2)
        assert "proc-abc123" in capsys.readouterr().out

    async def test_run_mode_calls_process_goal(self, capsys):
        from zebra_agent_web.cli import _goal_async

        result = MagicMock()
        result.run_id = "run-1"
        result.workflow_name = "Test WF"
        result.success = True
        result.tokens_used = 42
        result.error = None
        result.output = "Hello!"

        agent_loop = MagicMock()
        agent_loop.provider_name = "anthropic"
        agent_loop.process_goal = AsyncMock(return_value=result)

        engine = MagicMock()
        engine.store.get_processes_by_state = AsyncMock(return_value=[])

        with (
            patch("zebra_agent_web.api.agent_engine.ensure_initialized", new=AsyncMock()),
            patch("zebra_agent_web.api.agent_engine.get_agent_loop", return_value=agent_loop),
            patch("zebra_agent_web.api.engine.get_engine", return_value=engine),
        ):
            code = await _goal_async("Say hi", model="haiku", queue=False, priority=3)

        assert code == 0
        call = agent_loop.process_goal.call_args
        assert call.kwargs["goal"] == "Say hi"
        assert call.kwargs["model"] == "haiku"
        out = capsys.readouterr().out
        assert "Hello!" in out
        assert "Test WF" in out

    async def test_run_mode_kimi_switches_provider(self):
        from zebra_agent_web.cli import _goal_async

        result = MagicMock()
        result.success = True
        result.run_id = "r"
        result.workflow_name = "w"
        result.tokens_used = 0
        result.error = None
        result.output = None

        seen_providers = []

        agent_loop = MagicMock()
        agent_loop.provider_name = "anthropic"

        async def capture_process_goal(**kwargs):
            seen_providers.append(agent_loop.provider_name)
            return result

        agent_loop.process_goal = AsyncMock(side_effect=capture_process_goal)

        engine = MagicMock()
        engine.store.get_processes_by_state = AsyncMock(return_value=[])

        with (
            patch("zebra_agent_web.api.agent_engine.ensure_initialized", new=AsyncMock()),
            patch("zebra_agent_web.api.agent_engine.get_agent_loop", return_value=agent_loop),
            patch("zebra_agent_web.api.engine.get_engine", return_value=engine),
        ):
            await _goal_async("Say hi", model="kimi", queue=False, priority=3)

        assert seen_providers == ["kimi"]
        # restored afterwards
        assert agent_loop.provider_name == "anthropic"

    async def test_run_mode_failure_returns_nonzero(self):
        from zebra_agent_web.cli import _goal_async

        result = MagicMock()
        result.success = False
        result.run_id = "r"
        result.workflow_name = "w"
        result.tokens_used = 0
        result.error = "boom"
        result.output = None

        agent_loop = MagicMock()
        agent_loop.provider_name = "anthropic"
        agent_loop.process_goal = AsyncMock(return_value=result)

        engine = MagicMock()
        engine.store.get_processes_by_state = AsyncMock(return_value=[])

        with (
            patch("zebra_agent_web.api.agent_engine.ensure_initialized", new=AsyncMock()),
            patch("zebra_agent_web.api.agent_engine.get_agent_loop", return_value=agent_loop),
            patch("zebra_agent_web.api.engine.get_engine", return_value=engine),
        ):
            code = await _goal_async("Say hi", model="haiku", queue=False, priority=3)

        assert code == 1


# ---------------------------------------------------------------------------
# goals handler
# ---------------------------------------------------------------------------


class TestGoalsHandler:
    def _make_run(self, run_id: str, goal: str, success: bool):
        run = MagicMock()
        run.id = run_id
        run.goal = goal
        run.workflow_name = "Test Workflow"
        run.success = success
        run.started_at = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
        return run

    async def test_lists_runs(self, capsys):
        from zebra_agent_web.cli import _goals_async

        runs = [
            self._make_run("aaaabbbbcccc", "First goal", True),
            self._make_run("ddddeeeeffff", "Second goal", False),
        ]
        store = MagicMock()
        store.initialize = AsyncMock()
        store.get_recent_runs = AsyncMock(return_value=runs)

        with patch("zebra_agent_web.metrics_store.DjangoMetricsStore", return_value=store):
            code = await _goals_async(limit=5)

        assert code == 0
        store.get_recent_runs.assert_awaited_once_with(limit=5)
        out = capsys.readouterr().out
        assert "aaaabbbb" in out
        assert "First goal" in out
        assert "Test Workflow" in out

    async def test_empty_list(self, capsys):
        from zebra_agent_web.cli import _goals_async

        store = MagicMock()
        store.initialize = AsyncMock()
        store.get_recent_runs = AsyncMock(return_value=[])

        with patch("zebra_agent_web.metrics_store.DjangoMetricsStore", return_value=store):
            code = await _goals_async(limit=10)

        assert code == 0
        assert "No runs recorded yet." in capsys.readouterr().out
