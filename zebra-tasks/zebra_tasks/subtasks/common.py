"""Helpers shared by the sub-workflow actions.

The actions start their children and then suspend on them (``TaskResult.suspend``,
#146); the engine re-runs them with ``context.subflow_results`` once every child is
terminal (#181).
"""

from typing import Any

from zebra.tasks.base import ExecutionContext


async def start_child(context: ExecutionContext, process_id: str, timeout: Any = None) -> None:
    """Start a child process, bounding its inline auto-task chain by *timeout* seconds.

    A child still running its chain after *timeout* is failed (#142). Time it spends
    parked on a manual task is not counted.
    """
    if timeout:
        await context.engine.start_process_with_timeout(process_id, float(timeout))
    else:
        await context.engine.start_process(process_id)


def child_result(entry: dict[str, Any]) -> dict[str, Any]:
    """Turn a ``context.subflow_results`` entry into a sub-workflow result dict."""
    process_id = entry["process_id"]
    properties = entry.get("properties") or {}
    if entry.get("success"):
        return {
            "success": True,
            "process_id": process_id,
            "properties": properties,
            "output": properties.get("__output__"),
        }
    return {
        "success": False,
        "error": entry.get("error") or "Process failed",
        "process_id": process_id,
    }
