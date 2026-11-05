"""Where Commons-internal actions may run (#230, review fix).

``commons_adopt`` and ``commons_supervised_run`` must never be reachable from an
ordinary, LLM-written or imported workflow, and ``commons_adopt`` needs the journal's
record of every gate it relies on.
"""

from pathlib import Path

import pytest
from zebra.core.models import ProcessEvent, ProcessEventKind
from zebra.definitions.loader import load_definition_from_yaml
from zebra.tasks.registry import ActionRegistry

from zebra_tasks.agent.creator import check_generated_workflow
from zebra_tasks.commons.guard import (
    COMMONS_INTERNAL_ACTIONS,
    executable_shape,
    human_answer,
    internal_actions_used,
    is_import_workflow,
)
from zebra_tasks.commons.importing import CommonsAdoptAction, missing_gates
from zebra_tasks.commons.supervised import CommonsSupervisedRunAction
from zebra_tasks.llm.base import LLMResponse, TokenUsage

SHIPPED = Path(__file__).resolve().parents[2] / "zebra-agent" / "workflows" / "commons_import.yaml"


def _workflow(action: str, hook: bool = False) -> str:
    slot = "construct_action" if hook else "action"
    return f"""
name: "Sneaky"
first_task: a
tasks:
  a:
    name: "A"
    action: llm_call
  b:
    name: "B"
    {slot}: {action}
routings:
  - {{from: a, to: b}}
"""


def _response() -> LLMResponse:
    return LLMResponse("", None, "stop", TokenUsage(1, 1), "test/model")


@pytest.mark.parametrize("action", sorted(COMMONS_INTERNAL_ACTIONS))
@pytest.mark.parametrize("hook", [False, True])
def test_generated_workflows_may_not_use_commons_internal_actions(action, hook):
    definition = load_definition_from_yaml(_workflow(action, hook))
    assert [d.action for d in internal_actions_used(definition)] == [action]
    problem = check_generated_workflow(_response(), definition)
    assert problem and action in problem


def test_ordinary_generated_workflow_passes():
    definition = load_definition_from_yaml(_workflow("llm_call"))
    assert internal_actions_used(definition) == []
    assert check_generated_workflow(_response(), definition) is None


def test_internal_actions_are_hidden_from_the_creator_prompt():
    registry = ActionRegistry()
    registry.register_action("commons_adopt", CommonsAdoptAction)
    registry.register_action("commons_supervised_run", CommonsSupervisedRunAction)
    assert registry.describe_all(user_facing_only=True) == {}


def test_only_the_shipped_import_workflow_is_the_import_workflow():
    text = SHIPPED.read_text()
    shipped = load_definition_from_yaml(text)
    assert is_import_workflow(shipped)
    # Renamed, re-versioned or re-ided copies run the same thing: still it.
    renamed = shipped.model_copy(update={"id": "c:x", "name": "Other", "version": 9})
    assert executable_shape(renamed) == executable_shape(shipped)
    assert is_import_workflow(renamed)
    # One gate dropped: not it.
    tasks = {k: v for k, v in shipped.tasks.items() if k != "pii_scan"}
    assert not is_import_workflow(shipped.model_copy(update={"tasks": tasks}))


def _completed(task: str, route: str | None = None, changed: dict | None = None):
    return ProcessEvent(
        id=task,
        process_id="p",
        kind=ProcessEventKind.TASK_COMPLETED,
        task_definition_id=task,
        next_route=route,
        changed=changed or {},
    )


def test_missing_gates():
    owner = {"judge": _completed("judge", "proceed"), "pii_scan": _completed("pii_scan", "clean")}
    assert missing_gates(owner, owner_approved=True) is None
    assert missing_gates(owner, owner_approved=False) == "ethics"
    unattended = {
        **owner,
        "ethics": _completed("ethics", "proceed"),
        "gym": _completed("gym", "passed"),
        "trust": _completed("trust", "proceed"),
    }
    assert missing_gates(unattended, owner_approved=False) is None
    unattended["trust"] = _completed("trust", "approve")
    assert missing_gates(unattended, owner_approved=False) == "trust"
    assert missing_gates({}, owner_approved=True) == "judge"


def test_human_answer_comes_from_the_completion_event():
    steps = {
        "owner_approval": _completed(
            "owner_approval", changed={"__task_output_owner_approval": {"decision": "adopt"}}
        )
    }
    assert human_answer(steps, "owner_approval") == {"decision": "adopt"}
    assert human_answer(steps, "approve_run") is None
    # Completed without writing the answer (it was preset): no answer.
    assert human_answer({"owner_approval": _completed("owner_approval")}, "owner_approval") is None
