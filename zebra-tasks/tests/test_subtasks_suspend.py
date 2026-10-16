"""Sub-workflow actions suspend on their children instead of polling them (#181).

Uses a real engine + InMemoryStore, so suspension, resume and child state come from
the engine rather than mocks.
"""

import asyncio

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import (
    ProcessState,
    TaskInstance,
    TaskResult,
    TaskState,
)
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry

from zebra_tasks.subtasks import (
    ParallelSubworkflowsAction,
    SubworkflowAction,
    WaitForSubworkflowAction,
)


class _SetOutputAction(TaskAction):
    """Write the task's ``value`` (or the answer task's output) to ``__output__``."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        value = task.properties.get("value")
        if value is None:
            value = context.process.properties.get("__task_output_ask")
        context.set_process_property("__output__", value)
        return TaskResult.ok()


class _FailAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.fail("child broke")


class _SlowAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        await asyncio.sleep(5)
        return TaskResult.ok()


#: A child that waits on a human, then returns the answer as its output.
HUMAN_CHILD = {
    "id": "human_child",
    "name": "Human Child",
    "first_task_id": "ask",
    "tasks": {
        "ask": {"id": "ask", "name": "Ask", "auto": False},
        "emit": {"id": "emit", "name": "Emit", "action": "set_output"},
    },
    "routings": [{"id": "r1", "source_task_id": "ask", "dest_task_id": "emit"}],
}


def _child(child_id: str, action: str, **props) -> dict:
    return {
        "id": child_id,
        "name": child_id,
        "first_task_id": "only",
        "tasks": {"only": {"id": "only", "name": "Only", "action": action, "properties": props}},
        "routings": [],
    }


@pytest.fixture
def engine() -> WorkflowEngine:
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("subworkflow", SubworkflowAction)
    registry.register_action("wait_subworkflow", WaitForSubworkflowAction)
    registry.register_action("parallel_subworkflows", ParallelSubworkflowsAction)
    registry.register_action("set_output", _SetOutputAction)
    registry.register_action("fail", _FailAction)
    registry.register_action("slow", _SlowAction)
    return WorkflowEngine(InMemoryStore(), registry)


async def _run(engine: WorkflowEngine, yaml: str):
    definition = load_definition_from_yaml(yaml)
    await engine.store.save_definition(definition)
    process = await engine.create_process(definition)
    await engine.start_process(process.id)
    return await engine.store.load_process(process.id)


async def _answer_child(engine: WorkflowEngine, parent_id: str, answer: str) -> None:
    (child,) = await engine.store.list_child_processes(parent_id)
    (ask,) = await engine.get_pending_tasks(child.id)
    await engine.complete_task(ask.id, TaskResult.ok(output=answer))


async def _task(engine: WorkflowEngine, process_id: str, definition_id: str) -> TaskInstance:
    tasks = await engine.store.load_tasks_for_process(process_id)
    return next(t for t in tasks if t.task_definition_id == definition_id)


async def test_subworkflow_suspends_while_child_waits_on_human(engine):
    parent = await _run(
        engine,
        f"""
name: Parent
first_task_id: spawn
tasks:
  spawn:
    name: Spawn
    action: subworkflow
    properties:
      workflow: {HUMAN_CHILD}
      output_key: child_result
""",
    )

    spawn = await _task(engine, parent.id, "spawn")
    assert spawn.state == TaskState.AWAITING_SUBFLOW
    assert parent.state == ProcessState.RUNNING

    await _answer_child(engine, parent.id, "forty-two")

    parent = await engine.store.load_process(parent.id)
    assert parent.state == ProcessState.COMPLETE
    result = parent.properties["child_result"]
    assert result["success"] is True
    assert result["output"] == "forty-two"
    assert result["properties"]["__output__"] == "forty-two"


async def test_subworkflow_child_failure_fails_task(engine):
    parent = await _run(
        engine,
        f"""
name: Parent
first_task_id: spawn
tasks:
  spawn:
    name: Spawn
    action: subworkflow
    properties:
      workflow: {_child("broken", "fail")}
""",
    )

    assert parent.state == ProcessState.FAILED
    assert parent.properties["subworkflow_result"]["error"] == "child broke"


async def test_subworkflow_timeout_bounds_child_inline_run(engine):
    parent = await _run(
        engine,
        f"""
name: Parent
first_task_id: spawn
tasks:
  spawn:
    name: Spawn
    action: subworkflow
    properties:
      workflow: {_child("sleepy", "slow")}
      timeout: 0.2
""",
    )

    assert parent.state == ProcessState.FAILED
    (child,) = await engine.store.list_child_processes(parent.id)
    assert child.state == ProcessState.FAILED
    assert "Timed out" in parent.properties["subworkflow_result"]["error"]


async def test_wait_subworkflow_resumes_on_child_spawned_by_another_task(engine):
    parent = await _run(
        engine,
        f"""
name: Parent
first_task_id: spawn
tasks:
  spawn:
    name: Spawn
    action: subworkflow
    properties:
      workflow: {HUMAN_CHILD}
      wait: false
      output_key: child_id
  wait:
    name: Wait
    action: wait_subworkflow
    properties:
      process_id: "{{{{child_id}}}}"
      output_key: waited
routings:
  - from: spawn
    to: wait
""",
    )

    wait = await _task(engine, parent.id, "wait")
    assert wait.state == TaskState.AWAITING_SUBFLOW

    await _answer_child(engine, parent.id, "done later")

    parent = await engine.store.load_process(parent.id)
    assert parent.state == ProcessState.COMPLETE
    assert parent.properties["waited"]["success"] is True
    assert parent.properties["waited"]["output"] == "done later"


async def test_wait_subworkflow_on_child_that_already_finished(engine):
    """A child that completed inline before the wait suspends still resumes it."""
    parent = await _run(
        engine,
        f"""
name: Parent
first_task_id: spawn
tasks:
  spawn:
    name: Spawn
    action: subworkflow
    properties:
      workflow: {_child("quick", "set_output", value="instant")}
      wait: false
      output_key: child_id
  wait:
    name: Wait
    action: wait_subworkflow
    properties:
      process_id: "{{{{child_id}}}}"
      output_key: waited
routings:
  - from: spawn
    to: wait
""",
    )

    assert parent.state == ProcessState.COMPLETE
    assert parent.properties["waited"]["output"] == "instant"


async def test_parallel_subworkflows_keys_and_partial_failure(engine):
    parent = await _run(
        engine,
        f"""
name: Parent
first_task_id: fan_out
tasks:
  fan_out:
    name: Fan out
    action: parallel_subworkflows
    properties:
      workflows:
        - key: good
          workflow: {_child("good", "set_output", value="ok")}
        - key: bad
          workflow: {_child("bad", "fail")}
        - key: human
          workflow: {HUMAN_CHILD}
  all_ok:
    name: All ok
    action: set_output
    properties:
      value: all_ok
  some_failed:
    name: Some failed
    action: set_output
    properties:
      value: some_failed
routings:
  - from: fan_out
    to: all_ok
    condition: route_name
    name: success
  - from: fan_out
    to: some_failed
    condition: route_name
    name: partial_failure
""",
    )

    fan_out = await _task(engine, parent.id, "fan_out")
    assert fan_out.state == TaskState.AWAITING_SUBFLOW

    children = await engine.store.list_child_processes(parent.id)
    human = next(c for c in children if c.definition_id == "human_child")
    (ask,) = await engine.get_pending_tasks(human.id)
    await engine.complete_task(ask.id, TaskResult.ok(output="answered"))

    parent = await engine.store.load_process(parent.id)
    assert parent.state == ProcessState.COMPLETE
    results = parent.properties["parallel_results"]
    assert results["good"]["output"] == "ok"
    assert results["bad"] == {
        "success": False,
        "error": "child broke",
        "process_id": results["bad"]["process_id"],
    }
    assert results["human"]["output"] == "answered"
    assert parent.properties["__output__"] == "some_failed"
