"""#222: a continuation hands the previous run's own values to the goal workflow.

The goal workflow of a continued run gets the previous goal-workflow process's
properties as ``prior_outputs``, and inputs declaring ``from_prior`` are bound from
it. Uses a real engine + InMemoryStore.
"""

import json
import logging

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import (
    ProcessDefinition,
    ProcessState,
    TaskDefinition,
    TaskInstance,
    TaskResult,
)
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry

from zebra_tasks.agent.creator import WorkflowCreatorAction
from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction
from zebra_tasks.agent.followup import (
    MAX_PRIOR_OUTPUTS_CHARS,
    MAX_PRIOR_VALUE_CHARS,
    PRIOR_OUTPUTS_KEY,
    bind_prior_inputs,
    prior_outputs_from,
)
from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

INPUTS = {
    "type": "object",
    "properties": {
        "goal": {"type": "string"},
        "prior_brief": {"type": "string", "from_prior": "research_brief"},
    },
}

CHILD_DEF = ProcessDefinition(
    id="research_wf",
    name="Research",
    first_task_id="brief",
    properties={"result_key": "research_brief", "inputs": INPUTS},
    tasks={"brief": TaskDefinition(id="brief", name="Brief", action="brief")},
)

PARENT_DEF = ProcessDefinition(
    id="loop_wf",
    name="Loop",
    first_task_id="execute_workflow",
    tasks={
        "execute_workflow": TaskDefinition(
            id="execute_workflow",
            name="Execute Goal Workflow",
            action="execute_goal_workflow",
            properties={
                "workflow_name": "Research",
                "goal": "{{goal}}",
                "timeout": 5,
                "continue_on_failure": True,
            },
        ),
    },
)


class BriefAction(TaskAction):
    """Writes a brief that shows what the workflow saw of the previous run."""

    fail = False

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        seen = context.resolve_template("{{prior_outputs.research_brief}}")
        bound = context.get_process_property("prior_brief", "")
        context.set_process_property("research_brief", f"brief v{len(seen) and 2 or 1}")
        context.set_process_property("seen", seen)
        context.set_process_property("bound", bound)
        if BriefAction.fail:
            return TaskResult.fail("search timed out")
        return TaskResult.ok(output="briefed")


class _Library:
    definition = CHILD_DEF

    def get_workflow(self, name: str) -> ProcessDefinition:
        assert name == self.definition.name
        return self.definition


@pytest.fixture
def library():
    return _Library()


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def engine(store, library):
    BriefAction.fail = False
    registry = ActionRegistry()
    registry.register_action("execute_goal_workflow", ExecuteGoalWorkflowAction)
    registry.register_action("brief", BriefAction)
    return WorkflowEngine(store, registry, extras={"__workflow_library__": library})


async def _run(engine, store, run_id="run-1", previous_run_id=None, success=True):
    """Run the loop once; a continuation of *previous_run_id* when given."""
    props = {"goal": "Paddles for UK whitewater", "run_id": run_id}
    if previous_run_id:
        props["previous_run_context"] = {
            "run_id": previous_run_id,
            "workflow_name": "Research",
            "success": success,
        }
    root = await engine.create_process(PARENT_DEF, props)
    await engine.start_process(root.id)
    (child,) = await store.list_child_processes(root.id)
    return await store.load_process(child.id)


async def test_continuation_reads_prior_outputs_from_a_template(engine, store):
    first = await _run(engine, store)
    assert first.properties["research_brief"] == "brief v1"

    child = await _run(engine, store, run_id="run-2", previous_run_id="run-1")

    assert child.state == ProcessState.COMPLETE
    assert child.properties["seen"] == "brief v1"
    assert child.properties[PRIOR_OUTPUTS_KEY]["research_brief"] == "brief v1"


async def test_from_prior_input_is_bound(engine, store):
    await _run(engine, store)

    child = await _run(engine, store, run_id="run-2", previous_run_id="run-1")

    assert child.properties["prior_brief"] == "brief v1"
    assert child.properties["bound"] == "brief v1"


async def test_not_a_continuation_has_no_prior_outputs(engine, store):
    child = await _run(engine, store)

    assert PRIOR_OUTPUTS_KEY not in child.properties
    assert "prior_brief" not in child.properties
    assert child.properties["seen"] == ""


async def test_failed_previous_run_still_hands_over_its_outputs(engine, store):
    BriefAction.fail = True
    first = await _run(engine, store)
    assert first.state == ProcessState.FAILED
    BriefAction.fail = False

    child = await _run(engine, store, run_id="run-2", previous_run_id="run-1", success=False)

    assert child.properties["prior_brief"] == "brief v1"


async def test_chained_continuation_does_not_nest_prior_outputs(engine, store):
    await _run(engine, store)
    await _run(engine, store, run_id="run-2", previous_run_id="run-1")

    child = await _run(engine, store, run_id="run-3", previous_run_id="run-2")

    prior = child.properties[PRIOR_OUTPUTS_KEY]
    assert PRIOR_OUTPUTS_KEY not in prior
    assert prior["research_brief"] == "brief v2"


async def test_missing_previous_process_runs_without_prior_outputs(engine, store, caplog):
    with caplog.at_level(logging.WARNING, logger="zebra_tasks.agent.execute_workflow"):
        child = await _run(engine, store, run_id="run-2", previous_run_id="gone")

    assert child.state == ProcessState.COMPLETE
    assert PRIOR_OUTPUTS_KEY not in child.properties
    assert "No goal-workflow process for continued run gone" in caplog.text


def test_prior_outputs_leave_out_internal_and_oversized_values():
    long_text = "x" * 20000
    big_list = ["y" * 100] * 200
    assert len(json.dumps(big_list)) > MAX_PRIOR_VALUE_CHARS

    prior = prior_outputs_from(
        {
            "__task_output_brief": "internal",
            "goal": "Paddles",
            PRIOR_OUTPUTS_KEY: {"research_brief": "older"},
            "research_brief": "brief",
            "source_content": long_text,
            "search_results": big_list,
            "location": {"country": "UK"},
        }
    )

    assert prior == {
        "research_brief": "brief",
        "source_content": "x" * MAX_PRIOR_VALUE_CHARS,
        "location": {"country": "UK"},
    }


def test_prior_outputs_stay_within_the_total_cap():
    part = 7000
    props = {f"part{i}": "z" * part for i in range(6)}
    props["small"] = "kept"

    prior = prior_outputs_from(props)

    assert sum(len(v) for v in prior.values()) <= MAX_PRIOR_OUTPUTS_CHARS
    assert [k for k in prior if k.startswith("part")] == [
        f"part{i}" for i in range(MAX_PRIOR_OUTPUTS_CHARS // part)
    ]
    assert prior["small"] == "kept"  # a later value that still fits is kept


def test_bind_prior_inputs_skips_missing_keys_and_set_inputs():
    props = {"prior_brief": "typed by the user"}
    bind_prior_inputs(INPUTS, {"research_brief": "old"}, props)
    assert props["prior_brief"] == "typed by the user"

    props = {}
    bind_prior_inputs(INPUTS, {"summary": "old"}, props)
    assert props == {}

    bind_prior_inputs(None, {"research_brief": "old"}, props)
    assert props == {}


def test_from_prior_naming_an_excluded_or_dropped_key_stays_unset():
    inputs = {
        "properties": {
            "old_goal": {"from_prior": "goal"},
            "old_results": {"from_prior": "search_results"},
        }
    }
    prior = prior_outputs_from({"goal": "Paddles", "search_results": ["r" * 100] * 200})
    props = {}

    bind_prior_inputs(inputs, prior, props)

    assert props == {}


@pytest.mark.parametrize("action", [WorkflowCreatorAction, WorkflowOptimizerAction])
def test_workflow_authors_are_told_about_prior_outputs(action):
    prompt = action._PROMPT_HEADER + action._PROMPT_FOOTER

    assert "prior_outputs" in prompt
    assert "from_prior" in prompt
