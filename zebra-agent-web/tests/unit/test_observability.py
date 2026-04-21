"""Tests for F3 observability baseline — /health, /metrics, structlog, correlation ID."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rest_framework.test import APIClient

# ---------------------------------------------------------------------------
# /api/health/
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestHealthEndpoint:
    def test_health_returns_required_fields(self):
        client = APIClient()
        with (
            patch("zebra_agent_web.api.views.agent_engine") as mock_ae,
            patch("zebra_agent_web.api.views.engine") as mock_eng,
        ):
            mock_ae.ensure_initialized = AsyncMock()
            mock_store = AsyncMock()
            mock_store.count_processes_by_state = AsyncMock(return_value=3)
            mock_eng.get_engine.return_value.store = mock_store

            response = client.get("/api/health/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "daemon" in data
        assert "queue_depth" in data
        assert data["queue_depth"] == 3

    def test_health_unhealthy_on_error(self):
        client = APIClient()
        with patch("zebra_agent_web.api.views.agent_engine") as mock_ae:
            mock_ae.ensure_initialized = AsyncMock(side_effect=RuntimeError("db down"))
            response = client.get("/api/health/")

        assert response.status_code == 503
        assert response.json()["status"] == "unhealthy"


# ---------------------------------------------------------------------------
# /api/metrics/
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestMetricsEndpoint:
    def test_metrics_returns_prometheus_text(self):
        client = APIClient()
        with (
            patch("zebra_agent_web.api.views.agent_engine") as mock_ae,
            patch("zebra_agent_web.api.views.engine") as mock_eng,
        ):
            mock_bm = MagicMock()
            mock_bm.get_status = AsyncMock(
                return_value={"spent_today": 1.5, "available": 48.5, "paced_allowance": 50.0}
            )
            mock_ae.get_budget_manager.return_value = mock_bm

            mock_store = AsyncMock()
            mock_store.count_processes_by_state = AsyncMock(return_value=0)
            mock_eng.get_store.return_value = mock_store

            response = client.get("/api/metrics/")

        assert response.status_code == 200
        assert "text/plain" in response["Content-Type"]
        body = response.content.decode()
        assert "zebra_budget_spent_usd" in body
        assert "zebra_budget_remaining_usd" in body
        assert "zebra_queue_depth_total" in body

    def test_metrics_includes_goal_counters(self):
        from zebra_agent_web.api.metrics import REGISTRY, generate_latest

        body = generate_latest(REGISTRY).decode()
        assert "zebra_goals_submitted_total" in body
        assert "zebra_goals_completed_total" in body

    def test_metrics_tolerates_uninitialised_engine(self):
        """Gauges silently stay at 0 if engine hasn't started yet."""
        client = APIClient()
        with (
            patch("zebra_agent_web.api.views.agent_engine") as mock_ae,
            patch("zebra_agent_web.api.views.engine") as mock_eng,
        ):
            mock_ae.get_budget_manager.side_effect = RuntimeError("not ready")
            mock_eng.get_store.side_effect = RuntimeError("not ready")
            response = client.get("/api/metrics/")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Prometheus metric counters
# ---------------------------------------------------------------------------


class TestMetricCounters:
    def test_goals_submitted_increments(self):
        from zebra_agent_web.api.metrics import goals_submitted

        before = goals_submitted._value.get()
        goals_submitted.inc()
        assert goals_submitted._value.get() == before + 1

    def test_goals_completed_labels(self):
        from zebra_agent_web.api.metrics import goals_completed

        before_success = goals_completed.labels(status="success")._value.get()
        goals_completed.labels(status="success").inc()
        assert goals_completed.labels(status="success")._value.get() == before_success + 1

        goals_completed.labels(status="failed").inc()
        goals_completed.labels(status="timeout").inc()


# ---------------------------------------------------------------------------
# structlog / logging_config
# ---------------------------------------------------------------------------


class TestLoggingConfig:
    def test_configure_json_mode(self):
        """configure_logging(json_logs=True) should complete without error."""
        import logging

        from zebra_agent_web.logging_config import configure_logging

        configure_logging(json_logs=True)
        root = logging.getLogger()
        assert root.handlers

    def test_configure_dev_mode(self):
        """configure_logging(json_logs=False) should complete without error."""
        from zebra_agent_web.logging_config import configure_logging

        configure_logging(json_logs=False)


# ---------------------------------------------------------------------------
# Correlation ID in daemon logs
# ---------------------------------------------------------------------------


class TestDaemonCorrelationId:
    def test_tick_logs_run_id(self):
        """_tick() must include run_id in its log output when a process has one."""
        import asyncio
        from unittest.mock import patch

        from zebra.core.models import ProcessInstance, ProcessState
        from zebra_agent_web.api.daemon import _tick

        process = MagicMock(spec=ProcessInstance)
        process.id = "abcd1234-5678-0000-0000-000000000000"
        process.properties = {"goal": "test goal", "run_id": "test-run-42"}
        process.state = ProcessState.COMPLETE

        scheduler = AsyncMock()
        scheduler.pick_next = AsyncMock(return_value=process)

        budget_manager = AsyncMock()
        budget_manager.get_status = AsyncMock(
            return_value={"available": 10.0, "spent_today": 0.0, "paced_allowance": 50.0}
        )

        engine = AsyncMock()
        engine.start_process = AsyncMock()
        engine.store.load_process = AsyncMock(return_value=process)

        log_records: list = []

        def capture_log(msg, *args, **kwargs):
            log_records.append(msg % args if args else msg)

        async def run():
            halt_patch = patch(
                "zebra_agent_web.api.kill_switch.is_halted",
                new=AsyncMock(return_value=False),
            )
            with halt_patch, patch("zebra_agent_web.api.daemon.logger") as mock_logger:
                mock_logger.info.side_effect = capture_log
                mock_logger.warning.side_effect = capture_log
                mock_logger.error.side_effect = capture_log
                await _tick(
                    scheduler=scheduler,
                    budget_manager=budget_manager,
                    engine=engine,
                    dry_run=False,
                )

        asyncio.run(run())
        combined = " ".join(log_records)
        assert "test-run-42" in combined
