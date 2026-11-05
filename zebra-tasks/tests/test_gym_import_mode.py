"""Golden gym import mode (#230): test a received workflow before the owner sees it.

Only the candidate runs, on the offer's golden tasks plus local ones for the same
capability; strict actions only; never saves; anything it cannot judge escalates.
"""

import json
from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import TaskInstance, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_agent.library import WorkflowLibrary
from zebra_agent.storage.metrics import InMemoryMetricsStore

from zebra_tasks.agent.gym import RunGoldenGymAction
from zebra_tasks.agent.selector import WorkflowSelectorAction
from zebra_tasks.llm.base import LLMResponse, TokenUsage
from zebra_tasks.llm.client import set_llm_factory


class _AnswerAction(TaskAction):
    reversibility_hint = "always_reversible"

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        context.set_process_property("answer", task.properties.get("text", ""))
        return TaskResult.ok()


class _WriteAction(TaskAction):
    reversibility_hint = "context_dependent"

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        raise AssertionError("strict import mode must never run this")


class _Judge:
    model = "judge"

    async def complete(self, messages, **kwargs) -> LLMResponse:
        prompt = messages[-1].content
        criteria = prompt.split("## Criteria", 1)[1].split("## Workflow output", 1)[0]
        count = sum(1 for line in criteria.splitlines() if line[:1].isdigit())
        score = 1 if "Canberra" in prompt.split("## Workflow output", 1)[1] else 0
        verdict = {"criteria": [{"criterion": i + 1, "score": score} for i in range(count)]}
        return LLMResponse(json.dumps(verdict), None, "stop", TokenUsage(1, 1), "judge")


def _yaml(action: str = "answer", text: str = "Canberra") -> str:
    return f"""name: "Capital Facts"
version: 1
first_task: think
tasks:
  think:
    name: Think
    action: {action}
    properties: {{text: "{text}"}}
routings: []
"""


@pytest.fixture
def library(tmp_path: Path) -> WorkflowLibrary:
    golden = tmp_path / "golden"
    golden.mkdir()
    (golden / "local.yaml").write_text(
        "id: local_1\nworkflow: Capital Facts\ngoal: Capital of France?\n"
        "expected: Paris\ncriteria: [Names Canberra anyway]\n"
    )
    lib = WorkflowLibrary(tmp_path / "library", golden_path=golden)
    lib.ensure_initialized()
    return lib


@pytest.fixture
def engine(library) -> WorkflowEngine:
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("run_golden_gym", RunGoldenGymAction)
    registry.register_action("answer", _AnswerAction)
    registry.register_action("write", _WriteAction)
    set_llm_factory(lambda model: _Judge())
    return WorkflowEngine(
        InMemoryStore(),
        registry,
        extras={"__workflow_library__": library, "__metrics_store__": InMemoryMetricsStore()},
    )


GYM = """name: Import Gym
first_task: gym
tasks:
  gym:
    name: Gym
    action: run_golden_gym
    properties: {mode: import, offer: "{{offer}}", promote: true}
  passed: {name: Passed, action: answer, properties: {text: passed}}
  rejected: {name: Rejected, action: answer, properties: {text: rejected}}
  escalate: {name: Escalate, action: answer, properties: {text: escalate}}
routings:
  - {from: gym, to: passed, condition: route_name, name: passed}
  - {from: gym, to: rejected, condition: route_name, name: rejected}
  - {from: gym, to: escalate, condition: route_name, name: escalate}
"""


def _offer(yaml: str, golden=None) -> dict:
    return {
        "name": "Capital Facts",
        "content_sha256": "ab" * 32,
        "yaml": yaml,
        "golden_tasks": golden
        if golden is not None
        else [{"goal": "Capital of Australia?", "expected": "Canberra", "criteria": ["Canberra"]}],
    }


async def _gym(engine, offer: dict):
    process = await engine.create_process(
        load_definition_from_yaml(GYM), properties={"offer": offer}
    )
    await engine.start_process(process.id)
    return await engine.store.load_process(process.id)


async def test_scores_offer_and_local_golden_tasks_and_never_saves(engine, library):
    process = await _gym(engine, _offer(_yaml()))
    report = process.properties["golden_gym"]
    assert report["import"]["decision"] == "passed"
    assert sorted(report["import"]["golden_ids"]) == ["local_1", "offer-abababababab-1"]
    assert report["promote"] is False
    assert process.properties["answer"] == "passed"
    assert list(library.library_path.glob("*.yaml")) == []  # promote: true is ignored


async def test_low_score_routes_rejected(engine):
    process = await _gym(engine, _offer(_yaml(text="Sydney")))
    assert process.properties["golden_gym"]["import"]["decision"] == "rejected"
    assert process.properties["answer"] == "rejected"


async def test_non_reversible_action_escalates_without_running(engine):
    process = await _gym(engine, _offer(_yaml(action="write")))
    imp = process.properties["golden_gym"]["import"]
    assert imp["decision"] == "escalate" and "not always reversible" in imp["reason"]
    assert process.properties["golden_gym"]["scores"] == []
    assert process.properties["answer"] == "escalate"


@pytest.mark.parametrize("hook", ["construct_action", "destruct_action"])
async def test_process_level_hook_action_escalates_without_running(engine, hook):
    """A non-reversible action hidden in a top-level hook never runs in the gym."""
    yaml = _yaml().replace("first_task: think", f"{hook}: write\nfirst_task: think")
    assert getattr(load_definition_from_yaml(yaml), hook) == "write"
    process = await _gym(engine, _offer(yaml))  # _WriteAction raises if it ever runs
    imp = process.properties["golden_gym"]["import"]
    assert imp["decision"] == "escalate"
    assert f"the workflow {hook} 'write' is not always reversible" in imp["reason"]
    assert process.properties["golden_gym"]["scores"] == []
    assert process.properties["answer"] == "escalate"


async def test_no_golden_tasks_is_never_ungated(engine, library):
    for path in library.golden_path.glob("*.yaml"):
        path.unlink()
    process = await _gym(engine, _offer(_yaml(), golden=[]))
    assert process.properties["golden_gym"]["import"]["decision"] == "escalate"


async def test_invalid_offer_golden_tasks_are_skipped(engine, library):
    for path in library.golden_path.glob("*.yaml"):
        path.unlink()
    process = await _gym(engine, _offer(_yaml(), golden=[{"goal": "no criteria"}]))
    report = process.properties["golden_gym"]
    assert report["import"]["decision"] == "escalate"
    assert report["skipped"][0]["golden_id"] == "offer-abababababab-1"


async def test_selector_excludes_a_requested_workflow(engine, library):
    library.add_workflow(_yaml().replace("Capital Facts", "Imported One"))
    registry = engine.actions
    registry.register_action("workflow_selector", WorkflowSelectorAction)
    definition = load_definition_from_yaml(
        """name: Select
first_task: select
tasks:
  select:
    name: Select
    action: workflow_selector
    properties: {goal: "{{goal}}"}
routings: []
"""
    )
    process = await engine.create_process(
        definition,
        properties={
            "goal": "capitals",
            "requested_workflow": "Imported One",
            "__excluded_workflows__": ["Imported One"],
        },
    )
    await engine.start_process(process.id)
    process = await engine.store.load_process(process.id)
    # The requested workflow was refused by the owner: it is not used without asking
    assert process.properties.get("workflow_name") != "Imported One"
