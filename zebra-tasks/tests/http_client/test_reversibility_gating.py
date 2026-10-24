"""Trust gate and golden gym treat http_request as irreversible, http_get as reversible (F62)."""

from importlib.metadata import entry_points

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import TaskInstance, TaskState
from zebra.definitions import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, RouteNameCondition
from zebra.tasks.registry import ActionRegistry

from zebra_tasks.agent.creator import WorkflowCreatorAction
from zebra_tasks.agent.gym import unsafe_reason
from zebra_tasks.agent.trust_gate import DECISIONS_KEY, TrustGateAction
from zebra_tasks.http.actions import HttpGetAction, HttpRequestAction
from zebra_tasks.llm.client import set_llm_factory

GATED = """
id: gated_http
name: "Gated HTTP"
first_task_id: check_trust
tasks:
  check_trust:
    name: "Check Trust"
    action: trust_gate
    properties:
      domain: "integrations"
      target_task_id: call
  approve:
    name: "Approve call"
    auto: false
  call:
    name: "Call API"
    action: {action}
    properties:
      method: {method}
      url: "https://api.example.com/items"
routings:
  - from: check_trust
    to: call
    condition: route_name
    name: "proceed"
  - from: check_trust
    to: approve
    condition: route_name
    name: "approve"
"""


class SemiAutonomousStore:
    async def get_trust_level(self, user_id: int, domain: str) -> str:
        return "SEMI_AUTONOMOUS"


def _no_llm(model):
    raise AssertionError("the class hint must decide without an LLM call")


@pytest.fixture
def no_llm():
    previous = set_llm_factory(_no_llm)
    yield
    set_llm_factory(previous)


@pytest.fixture
def engine():
    registry = ActionRegistry()
    registry.register_action("trust_gate", TrustGateAction)
    registry.register_action("http_get", HttpGetAction)
    registry.register_action("http_request", HttpRequestAction)
    registry.register_condition("route_name", RouteNameCondition)
    return WorkflowEngine(
        InMemoryStore(), registry, extras={"__trust_store__": SemiAutonomousStore()}
    )


async def _gate_decision(engine, action: str, method: str) -> dict:
    """Run only the gate task: the gated call itself is not under test here."""
    definition = load_definition_from_yaml(GATED.format(action=action, method=method))
    process = await engine.create_process(definition, properties={"__user_id__": 1})
    gate_def = definition.tasks["check_trust"]
    task = TaskInstance(
        id="gate-1",
        process_id=process.id,
        task_definition_id="check_trust",
        state=TaskState.RUNNING,
        foe_id="foe-1",
        properties=dict(gate_def.properties),
    )
    context = ExecutionContext(
        engine=engine,
        store=engine.store,
        process=process,
        process_definition=definition,
        task_definition=gate_def,
        extras=engine.extras,
    )
    result = await TrustGateAction().run(task, context)
    return {"route": result.next_route, **context.process.properties[DECISIONS_KEY][-1]}


async def test_gate_sends_http_request_to_approval_without_llm(engine, no_llm):
    decision = await _gate_decision(engine, "http_request", "POST")
    assert decision["route"] == "approve"
    assert decision["assessment"]["reversible"] is False
    assert decision["assessment"]["source"] == "hint"


async def test_gate_lets_http_get_proceed_without_llm(engine, no_llm):
    decision = await _gate_decision(engine, "http_get", "GET")
    assert decision["route"] == "proceed"
    assert decision["assessment"]["reversible"] is True


def test_gym_refuses_http_request_but_not_http_get(engine):
    write = load_definition_from_yaml(
        GATED.format(action="http_request", method="DELETE").replace("auto: false", "auto: true")
    )
    read = load_definition_from_yaml(
        GATED.format(action="http_get", method="GET").replace("auto: false", "auto: true")
    )
    assert unsafe_reason(write, engine.actions) == "action 'http_request' is irreversible"
    assert unsafe_reason(read, engine.actions) is None


def test_actions_are_registered_entry_points():
    registered = {ep.name: ep.value for ep in entry_points(group="zebra.tasks")}
    assert registered["http_get"] == "zebra_tasks.http.actions:HttpGetAction"
    assert registered["http_request"] == "zebra_tasks.http.actions:HttpRequestAction"


def test_creator_prompt_lists_http_request_as_side_effecting():
    footer = WorkflowCreatorAction._PROMPT_FOOTER
    rule = footer[footer.index("10. Only use actions") :]
    assert "http_request" in rule.split("\n\n")[0]
