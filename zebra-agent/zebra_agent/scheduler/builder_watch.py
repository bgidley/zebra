"""BuilderWatcher — hand host-builder results back to waiting workflows (#98, #172).

A workflow that asks the host builder for a build (``claude_code_build``) or a publish
(``publish_build``) then parks on an external-wait task::

    await_build:
      auto: false
      properties: {external: builder, job_key: build_job, wait_for: result}

``tick()`` runs on every daemon tick. For each READY ``external: builder`` task whose job has an
answer in the spool (``result.json``, or ``published.json`` for ``wait_for: published``) it
completes the task with that answer, routed by its state, as the web UI completes a human task.
It also asks the builder to cancel any job whose process has already ended, so an abandoned build
stops using the subscription.

Completions run in the background (the rest of the workflow runs inline after a completion), so a
tick never waits on them.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from zebra.core.models import ProcessState, TaskResult, TaskState

if TYPE_CHECKING:
    from zebra.core.engine import WorkflowEngine
    from zebra.core.models import TaskInstance
    from zebra_tasks.builder.spool import BuilderSpool

logger = logging.getLogger(__name__)

EXTERNAL = "builder"
VIOLATIONS_KEY = "__builder_violations__"
_ENDED = {ProcessState.COMPLETE, ProcessState.FAILED}


class BuilderWatcher:
    """Complete external-wait tasks from builder answers; cancel builds whose goal ended."""

    def __init__(self, engine: WorkflowEngine, spool: BuilderSpool) -> None:
        self._engine = engine
        self._spool = spool
        self._in_flight: dict[str, asyncio.Task] = {}

    async def tick(self) -> int:
        """One pass. Returns the number of waits handed an answer."""
        self._in_flight = {k: t for k, t in self._in_flight.items() if not t.done()}
        delivered = 0
        for task in await self._engine.store.get_ready_tasks():
            if task.id in self._in_flight:
                continue
            answer = await self._answer_for(task)
            if answer is None:
                continue
            output, route = answer
            self._in_flight[task.id] = asyncio.create_task(
                self._complete(task, output, route), name=f"builder-wait-{task.id[:12]}"
            )
            delivered += 1
        await self._cancel_orphans()
        return delivered

    async def drain(self) -> None:
        """Wait for in-flight completions (tests and shutdown)."""
        if self._in_flight:
            await asyncio.gather(*self._in_flight.values(), return_exceptions=True)

    async def _answer_for(self, task: TaskInstance) -> tuple[dict, str] | None:
        """``(output, route)`` for a builder wait whose job has answered, else None."""
        store = self._engine.store
        process = await store.load_process(task.process_id)
        if process is None or process.state != ProcessState.RUNNING:
            return None
        definition = await store.load_definition(process.definition_id)
        task_def = definition.tasks.get(task.task_definition_id) if definition else None
        if task_def is None or task_def.auto:
            return None
        props = task_def.properties or {}
        if props.get("external") != EXTERNAL:
            return None

        job = (process.properties or {}).get(props.get("job_key", "build_job"))
        job_id = job.get("job_id") if isinstance(job, dict) else None
        if not job_id:
            return {"state": "failed", "error": "no build job recorded for this wait"}, "failed"

        try:
            if props.get("wait_for", "result") == "published":
                published = self._spool.published(job_id)
                if published is None:
                    return None
                route = "publish_failed" if published.get("error") else "published"
                return published, route
            result = self._spool.result(job_id)
        except ValueError:
            return {"state": "failed", "error": f"bad build job id {job_id!r}"}, "failed"
        if result is None:
            return None
        return result, str(result.get("state") or "failed")

    async def _complete(self, task: TaskInstance, output: dict, route: str) -> None:
        try:
            violations = output.get("violations") or []
            if violations:
                await self._record_violations(task.process_id, output.get("job_id"), violations)
            current = await self._engine.store.load_task(task.id)
            if current is None or current.state != TaskState.READY:
                return
            logger.info("Builder answered %s for task %s", route, task.id[:12])
            await self._engine.complete_task(
                task.id, TaskResult(success=True, output=output, next_route=route)
            )
        except Exception:
            logger.exception("Could not complete builder wait %s", task.id[:12])

    async def _record_violations(self, process_id: str, job_id: str | None, violations: list):
        """Append capability-budget breaches to the process record (#172)."""
        store = self._engine.store
        process = await store.load_process(process_id)
        if process is None:
            return
        recorded = list(process.properties.get(VIOLATIONS_KEY, []))
        at = datetime.now(UTC).isoformat()
        recorded.extend({"job_id": job_id, "at": at, **v} for v in violations)
        process.properties[VIOLATIONS_KEY] = recorded
        await store.save_process(process.model_copy(update={"updated_at": datetime.now(UTC)}))

    async def _cancel_orphans(self) -> None:
        for job_id, process_id in self._spool.live_jobs():
            process = await self._engine.store.load_process(process_id) if process_id else None
            if process is None or process.state in _ENDED:
                logger.info("Cancelling build job %s: its process has ended", job_id[:12])
                try:
                    self._spool.cancel(job_id)
                except (OSError, ValueError):
                    logger.warning("Could not cancel build job %s", job_id[:12], exc_info=True)
