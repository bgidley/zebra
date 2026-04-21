"""Prometheus metric definitions for Zebra Agent.

All metrics use a private CollectorRegistry so they don't collide with
any default prometheus_client globals in tests.  The ``metrics_view``
in views.py refreshes gauges from live data on each scrape, then calls
``generate_latest(REGISTRY)``.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    generate_latest,
)

REGISTRY = CollectorRegistry(auto_describe=True)

# Counters — monotonically increasing event counts
goals_submitted = Counter(
    "zebra_goals_submitted_total",
    "Goals submitted via the API",
    registry=REGISTRY,
)
goals_completed = Counter(
    "zebra_goals_completed_total",
    "Goals completed by the daemon",
    ["status"],  # label: success | failed | timeout
    registry=REGISTRY,
)

# Gauges — point-in-time values refreshed on each /metrics scrape
budget_spent_usd = Gauge(
    "zebra_budget_spent_usd",
    "Daily LLM budget spent so far (USD)",
    registry=REGISTRY,
)
budget_remaining_usd = Gauge(
    "zebra_budget_remaining_usd",
    "Daily LLM budget remaining (paced, USD)",
    registry=REGISTRY,
)
queue_depth = Gauge(
    "zebra_queue_depth_total",
    "CREATED (queued) processes waiting for the daemon",
    registry=REGISTRY,
)

__all__ = [
    "REGISTRY",
    "CONTENT_TYPE_LATEST",
    "generate_latest",
    "goals_submitted",
    "goals_completed",
    "budget_spent_usd",
    "budget_remaining_usd",
    "queue_depth",
]
