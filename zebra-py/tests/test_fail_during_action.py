"""A process failed while one of its actions runs stays failed (#183).

``fail_process`` can be called from outside the chain that is running an action
(e.g. a parent goal's timeout). When the action finally returns, its result must
be discarded: no routing on a dead process, and no stale save reverting it to
RUNNING.
"""

import asyncio

from zebra.core.engine import WorkflowEngine
from zebra.core.models import (
    ProcessDefinition,
    ProcessState,
    RoutingDefinition,
    TaskDefinition,
    TaskInstance,
    TaskResult,
    TaskState,
)
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry

started = asyncio.Event()
release = asyncio.Event()


class _BlockingAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        started.set()
        await release.wait()
        return TaskResult.ok(output="late result")


async def test_result_is_discarded_when_process_failed_mid_action():
    started.clear()
    release.clear()
    store = InMemoryStore()
    registry = ActionRegistry()
    registry.register_action("block", _BlockingAction)
    engine = WorkflowEngine(store, registry)
    definition = ProcessDefinition(
        id="blocking",
        name="Blocking",
        first_task_id="work",
        tasks={
            "work": TaskDefinition(id="work", name="Work", action="block"),
            "after": TaskDefinition(id="after", name="After"),
        },
        routings=[RoutingDefinition(id="r1", source_task_id="work", dest_task_id="after")],
    )
    process = await engine.create_process(definition)

    run = asyncio.create_task(engine.start_process(process.id))
    await started.wait()
    await engine.fail_process(process.id, "Timeout after 600s")
    release.set()
    await run

    process = await store.load_process(process.id)
    assert process.state == ProcessState.FAILED
    assert process.properties["__error__"] == "Timeout after 600s"
    assert "__task_output_work" not in process.properties
    tasks = await store.load_tasks_for_process(process.id)
    assert {t.task_definition_id: t.state for t in tasks} == {"work": TaskState.FAILED}
