"""Views that run tasks must initialise the agent, not just the engine (#231).

The agent's initialisation injects the engine extras (library, stores, Commons publisher …).
``human_task_submit`` only initialised the bare engine, so after a restart the first approval
ran its follow-on tasks with no extras: *Commons Offer* failed closed with "no publisher or
library". Any view that completes, retries or fails a task must call
``agent_engine.ensure_initialized()``.
"""

import re
from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[2] / "zebra_agent_web" / "api"
RUNS_TASKS = ("complete_task(", "retry_review_task(", "fail_review_task(")


def _functions(source: str):
    """``(name, body)`` of each top-level function in a module."""
    for part in re.split(r"\n(?=(?:@[^\n]*\n)*(?:async )?def )", source):
        match = re.match(r"(?:@[^\n]*\n)*(?:async )?def (\w+)", part)
        if match:
            yield match.group(1), part


@pytest.mark.parametrize("module", ["web_views.py", "views.py"])
def test_task_running_views_initialise_the_agent(module):
    runners = {
        name: body
        for name, body in _functions((API / module).read_text())
        if any(call in body for call in RUNS_TASKS)
    }
    assert runners, f"no task-running views found in {module}"
    missing = [n for n, body in runners.items() if "agent_engine.ensure_initialized()" not in body]
    assert not missing, f"{module}: {missing} run tasks without agent_engine.ensure_initialized()"


def test_human_task_submit_is_checked():
    names = {n for n, b in _functions((API / "web_views.py").read_text()) if "complete_task(" in b}
    assert "human_task_submit" in names
