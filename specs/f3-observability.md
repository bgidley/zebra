---
name: f3-observability
description: Observability baseline — structured JSON logging, Prometheus metrics, health check endpoint
metadata:
  type: feature-spec
  issue: "#3"
  requirement: REQ-NFR-004
  status: implemented
---

# F3: Observability Baseline

**GitLab issue**: #3  
**Requirement**: REQ-NFR-004  
**Status**: Implemented (correlation ID partially implemented)

## Goal & scope

`/health` endpoint, structured JSON logging via `structlog`, Prometheus metrics at `/metrics`. Correlation ID per process propagated from web request through daemon to task log.

## Logging

**Module**: `zebra_agent_web/logging_config.py`  
`configure_logging(json_logs: bool)` is called at `settings.py` import time (`json_logs=not DEBUG`).

Structlog processor chain:
- `merge_contextvars` — picks up any bound context vars
- `add_log_level`, `add_logger_name`, `TimeStamper(fmt="iso")`
- JSON output in production, `ConsoleRenderer` in DEBUG mode

All stdlib `logging.getLogger(__name__)` calls automatically route through structlog.

## Metrics

**Module**: `zebra_agent_web/api/metrics.py`  
Private `CollectorRegistry` (no collision with default globals). Metrics refreshed from live data on each scrape.

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `zebra_goals_submitted_total` | Counter | — | Goals submitted via API |
| `zebra_goals_completed_total` | Counter | `status` (success/failed/timeout) | Goals completed by daemon |
| `zebra_budget_spent_usd` | Gauge | — | Daily LLM spend |
| `zebra_budget_remaining_usd` | Gauge | — | Paced remaining budget |
| `zebra_queue_depth_total` | Gauge | — | CREATED processes awaiting daemon |

**Endpoint**: `GET /api/metrics/` — returns Prometheus text format.

## Health check

**Endpoint**: `GET /api/health/` (`AllowAny` — no auth required)  

Success (200):
```json
{"status": "healthy", "agent": "initialized", "daemon": "running|not_started", "queue_depth": N}
```

Error (503):
```json
{"status": "unhealthy", "error": "..."}
```

Both `/api/health/` and `/api/metrics/` are in `_ALWAYS_ALLOWED` in `middleware.py` — bypass setup-redirect and auth.

## Correlation ID

**Partially implemented.** `structlog.merge_contextvars` is wired, enabling `bind_contextvars(run_id=...)` anywhere in the call stack. The daemon includes `run_id` inline in log messages (e.g. `[daemon:pick] ... run_id=test-run-42`). No HTTP middleware currently calls `bind_contextvars` per web request — per-request correlation IDs are not propagated from the web layer.

## Open questions / risks

- **No per-request correlation ID middleware** — HTTP request tracing is absent; only daemon/background runs carry a `run_id`.
- **No OpenTelemetry tracing** — F78 covers this as a future enabler.
- **`prometheus_client` version pinning** — `CONTENT_TYPE_LATEST` import must stay in sync with the installed version.
