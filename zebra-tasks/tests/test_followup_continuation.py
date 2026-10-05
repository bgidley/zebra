"""Tests for goal continuation context (F134)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from zebra_agent.metrics import TaskExecution, WorkflowRun
from zebra_agent.storage.metrics import InMemoryMetricsStore

from zebra_tasks.agent.followup import (
    CONTINUATION_COMMENT_KEY,
    MAX_CHAIN_LINKS,
    MAX_TASK_TEXT_CHARS,
    MAX_TASKS,
    PREVIOUS_RUN_CONTEXT_KEY,
    build_previous_run_context,
    load_previous_run_context,
    with_previous_run,
)


def _run(run_id: str, *, success: bool = True, extends: str | None = None, **kw) -> WorkflowRun:
    now = datetime.now(UTC)
    return WorkflowRun(
        id=run_id,
        workflow_name=kw.pop("workflow_name", "Research"),
        goal=kw.pop("goal", "Find five sources on X"),
        started_at=now,
        completed_at=kw.pop("completed_at", now),
        success=success,
        output=kw.pop("output", f"output of {run_id}"),
        extends_run_id=extends,
        **kw,
    )


def _exec(run_id: str, order: int, state: str, **kw) -> TaskExecution:
    return TaskExecution(
        id=f"{run_id}-{order}",
        run_id=run_id,
        task_definition_id=f"task_{order}",
        task_name=f"Task {order}",
        execution_order=order,
        state=state,
        started_at=datetime.now(UTC),
        **kw,
    )


# --- build_previous_run_context ---------------------------------------------


def test_build_includes_task_progress_in_order_and_truncated():
    execs = [
        _exec("r1", 2, "failed", error="E" * 1000),
        _exec("r1", 1, "complete", output={"found": ["a", "b"]}),
    ]
    ctx = build_previous_run_context(_run("r1", success=False, error="boom"), execs)

    assert [t["task"] for t in ctx["tasks"]] == ["Task 1", "Task 2"]
    assert ctx["tasks"][0] == {
        "task": "Task 1",
        "state": "complete",
        "output": '{"found": ["a", "b"]}',
    }
    assert ctx["tasks"][1]["state"] == "failed"
    assert len(ctx["tasks"][1]["error"]) == MAX_TASK_TEXT_CHARS
    assert ctx["error"] == "boom"
    assert ctx["success"] is False


def test_build_caps_task_count():
    execs = [_exec("r1", i, "complete") for i in range(1, MAX_TASKS + 10)]
    ctx = build_previous_run_context(_run("r1"), execs)
    assert len(ctx["tasks"]) == MAX_TASKS


def test_build_chain_is_summary_capped_and_not_nested():
    chain = [
        _run(f"r{i}", continuation_comment=f"comment {i}", goal="G" * 500)
        for i in range(MAX_CHAIN_LINKS + 3)
    ]
    ctx = build_previous_run_context(_run("leaf"), chain=chain)

    assert len(ctx["chain"]) == MAX_CHAIN_LINKS
    assert ctx["chain"][-1]["run_id"] == f"r{MAX_CHAIN_LINKS + 2}"
    assert ctx["chain"][-1]["comment"] == f"comment {MAX_CHAIN_LINKS + 2}"
    assert len(ctx["chain"][0]["goal"]) == 200
    assert set(ctx["chain"][0]) == {"run_id", "goal", "workflow_name", "success", "comment"}


def test_build_without_extras_matches_f116_shape():
    ctx = build_previous_run_context(_run("r1"))
    assert set(ctx) == {"run_id", "goal", "workflow_name", "success", "output"}


# --- with_previous_run -------------------------------------------------------


def test_with_previous_run_leads_with_continuation_comment_and_progress():
    ctx = build_previous_run_context(
        _run("r2", success=False),
        [_exec("r2", 1, "complete", output="2 sources"), _exec("r2", 2, "failed", error="timeout")],
        chain=[_run("r1", workflow_name="Search", goal="Find five sources on X")],
    )
    text = with_previous_run(
        "Find five sources on X",
        {PREVIOUS_RUN_CONTEXT_KEY: ctx, CONTINUATION_COMMENT_KEY: "Only got 2; get 3 more"},
    )

    assert text.startswith("Find five sources on X\n")
    assert "continues a previous run" in text
    assert "<continuation_comment>\nOnly got 2; get 3 more\n</continuation_comment>" in text
    assert "Outcome: failed" in text
    assert "- Task 1 [complete]: 2 sources" in text
    assert "- Task 2 [failed]: timeout" in text
    assert "<earlier_runs>" in text and "Search (succeeded)" in text


def test_with_previous_run_without_comment_is_plain_follow_up():
    ctx = build_previous_run_context(_run("r1"))
    text = with_previous_run("Shorter please", {PREVIOUS_RUN_CONTEXT_KEY: ctx})
    assert "follow-up to a previous run" in text
    assert "<continuation_comment>" not in text
    assert "<earlier_runs>" not in text


# --- load_previous_run_context -----------------------------------------------


async def test_load_includes_progress_and_chain_for_failed_run():
    store = InMemoryMetricsStore()
    await store.record_run(_run("root"))
    await store.record_run(
        _run("mid", success=False, extends="root", continuation_comment="keep going")
    )
    await store.record_task_executions([_exec("mid", 1, "failed", error="rate limited")])

    ctx = await load_previous_run_context(store, "mid")

    assert ctx["run_id"] == "mid"
    assert ctx["success"] is False
    assert ctx["comment"] == "keep going"
    assert ctx["tasks"] == [{"task": "Task 1", "state": "failed", "error": "rate limited"}]
    assert [c["run_id"] for c in ctx["chain"]] == ["root"]


async def test_load_returns_none_for_unknown_or_unfinished_run():
    store = InMemoryMetricsStore()
    await store.record_run(_run("running", completed_at=None))
    assert await load_previous_run_context(store, "running") is None
    assert await load_previous_run_context(store, "missing") is None
    assert await load_previous_run_context(store, "") is None
    assert await load_previous_run_context(None, "running") is None


async def test_load_degrades_when_task_executions_fail():
    store = InMemoryMetricsStore()
    await store.record_run(_run("r1", completed_at=datetime.now(UTC) - timedelta(hours=1)))
    store.get_task_executions = AsyncMock(side_effect=RuntimeError("db down"))

    ctx = await load_previous_run_context(store, "r1")

    assert ctx["run_id"] == "r1"
    assert "tasks" not in ctx
