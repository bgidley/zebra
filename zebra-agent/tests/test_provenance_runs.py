"""Stamped and legacy workflows are selected and run end to end (#270, follow-up to #229).

A goal driver ``workflow_selector`` → ``execute_goal_workflow`` runs on a real engine and
library. The selector's LLM is scripted to pick one workflow; the goal workflow's step records
which workflow ran. One library workflow is saved through the library (it has a ``commons``
block), the other is a file written before provenance existed (no block).
"""

import json
from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskInstance, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction
from zebra_tasks.agent.selector import WorkflowSelectorAction
from zebra_tasks.llm.base import LLMProvider, LLMResponse, TokenUsage
from zebra_tasks.llm.client import set_llm_factory

from zebra_agent.library import WorkflowLibrary
from zebra_agent.provenance import content_sha256, read_commons

STAMPED = """name: "Stamped Plan"
description: "Plan a trip (saved through the library)"
tags: [planning]
version: 1
first_task: work
tasks:
  work:
    name: "Work"
    action: record_run
    properties:
      label: stamped
"""

LEGACY = (
    STAMPED.replace("Stamped Plan", "Legacy Plan")
    .replace("saved through the library", "written before provenance")
    .replace("label: stamped", "label: legacy")
)

DRIVER = """
name: Goal Driver
first_task_id: select
tasks:
  select:
    name: Select
    action: workflow_selector
    properties: {goal: "{{goal}}"}
  run:
    name: Run
    action: execute_goal_workflow
    properties:
      workflow_name: "{{workflow_name}}"
      goal: "{{goal}}"
routings:
  - {from: select, to: run, condition: route_name, name: use_existing}
"""


class _RecordRun(TaskAction):
    """The goal workflow's only step: note which workflow ran."""

    description = "Test step"
    reversibility_hint = "always_reversible"
    ran: list[str] = []

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        label = task.properties["label"]
        _RecordRun.ran.append(label)
        context.set_process_property("answer", f"ran {label}")
        return TaskResult.ok(output=f"ran {label}")


class _Selector(LLMProvider):
    """Answers the selector with one workflow name and keeps the prompt it was shown."""

    def __init__(self, pick: str) -> None:
        self.pick = pick
        self.prompts: list[str] = []

    async def complete(self, messages, tools=None, temperature=0.7, max_tokens=4096, **kw):
        self.prompts.append(messages[-1].content)
        reply = {
            "workflow_name": self.pick,
            "create_new": False,
            "create_variant": False,
            "reasoning": "fits",
        }
        return LLMResponse(
            content=json.dumps(reply),
            tool_calls=None,
            finish_reason="end_turn",
            usage=TokenUsage(10, 5),
            model="test/model",
        )

    async def stream(self, messages, tools=None, temperature=0.7, max_tokens=4096):
        raise NotImplementedError
        yield ""

    @property
    def name(self) -> str:
        return "scripted"

    @property
    def model(self) -> str:
        return "test/model"

    @property
    def max_context_tokens(self) -> int:
        return 200_000


@pytest.fixture
def library(tmp_path: Path) -> WorkflowLibrary:
    lib = WorkflowLibrary(tmp_path / "workflows", owner_user_id=1, sphere="home")
    lib.ensure_initialized()
    lib.add_workflow(STAMPED, llm_defined=True, writer="creator")
    (lib.library_path / "legacy_plan.yaml").write_text(LEGACY)
    return lib


@pytest.fixture
def engine(library: WorkflowLibrary) -> WorkflowEngine:
    _RecordRun.ran = []
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("record_run", _RecordRun)
    registry.register_action("workflow_selector", WorkflowSelectorAction)
    registry.register_action("execute_goal_workflow", ExecuteGoalWorkflowAction)
    return WorkflowEngine(InMemoryStore(), registry, extras={"__workflow_library__": library})


async def _run_goal(engine: WorkflowEngine, pick: str) -> tuple[dict, _Selector]:
    selector = _Selector(pick)
    set_llm_factory(lambda model: selector)
    process = await engine.create_process(
        load_definition_from_yaml(DRIVER), properties={"goal": "Plan a weekend trip"}
    )
    await engine.start_process(process.id)
    done = await engine.store.load_process(process.id)
    assert done.state == ProcessState.COMPLETE, done.properties
    return done.properties, selector


def test_fixture_has_one_stamped_and_one_legacy_workflow(library):
    stamped = read_commons((library.library_path / "stamped_plan.yaml").read_text())
    assert stamped["content_sha256"] == content_sha256(STAMPED)
    assert read_commons(LEGACY) is None


@pytest.mark.parametrize(
    "pick,label",
    [("Stamped Plan", "stamped"), ("Legacy Plan", "legacy")],
)
async def test_selected_workflow_runs_end_to_end(engine, pick, label):
    props, selector = await _run_goal(engine, pick)

    # Both workflows were offered to the selector, whatever their provenance.
    (prompt,) = selector.prompts
    assert "- Stamped Plan:" in prompt and "- Legacy Plan:" in prompt
    # The picked one ran and the goal completed with its output.
    assert props["workflow_name"] == pick
    assert _RecordRun.ran == [label]
    result = props["execution_result"]
    assert result["success"] is True, result
    assert result["output"] == f"ran {label}"
