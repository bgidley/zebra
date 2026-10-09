"""ExecuteGoalWorkflowAction reports the user's human-task answers (F152)."""

from zebra.definitions.loader import load_definition_from_yaml

from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction

_YAML = """
name: "Commute"
first_task: ask
tasks:
  ask:
    name: "Where from?"
    auto: false
    properties:
      schema:
        type: object
        properties:
          goal:
            type: string
            readOnly: true
          origin:
            type: string
  skipped:
    name: "Never answered"
    auto: false
  plan:
    name: "Plan"
    action: llm_call
    properties:
      prompt: hi
routings:
  - from: ask
    to: plan
  - from: skipped
    to: plan
"""


def test_user_inputs_are_human_task_answers_without_readonly_fields():
    definition = load_definition_from_yaml(_YAML)
    properties = {
        "__task_output_ask": {"goal": "plan my commute", "origin": "York"},
        "__task_output_plan": "Take the train",
    }
    inputs = ExecuteGoalWorkflowAction._extract_user_inputs(properties, definition)
    assert inputs == {"Where from?": {"origin": "York"}}
