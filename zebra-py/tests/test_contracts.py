"""Workflow output contracts: static checks and strict templates (#271)."""

import pytest

from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskInstance, TaskResult
from zebra.definitions.contracts import (
    ERROR,
    WARNING,
    validate_contracts,
    validate_output_schema,
)
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry


def load(yaml_text: str):
    return load_definition_from_yaml(yaml_text)


LINEAR = """
name: linear
tasks:
  a: {name: A, action: ok}
  b:
    name: B
    action: ok
    properties: {prompt: "use {{a.output}} and {{goal}}"}
routings:
  - {from: a, to: b}
"""

BRANCHES = """
name: branches
tasks:
  start: {name: Start, action: ok}
  draft: {name: Draft, action: ok}
  skip: {name: Skip, action: ok}
  merge:
    name: Merge
    action: ok
    synchronized: %s
    properties: {prompt: "{{draft.output}}"}
routings:
  - {from: start, to: draft, parallel: %s, condition: route_name, name: approved}
  - {from: start, to: skip, parallel: %s, condition: route_name, name: rejected}
  - {from: draft, to: merge}
  - {from: skip, to: merge}
"""


def test_valid_workflow_has_no_findings():
    assert validate_contracts(load(LINEAR)) == []


def test_unknown_task_is_an_error_naming_task_and_reference():
    definition = load(LINEAR.replace("{{a.output}}", "{{ghost.output}}"))

    (finding,) = validate_contracts(definition)

    assert finding.severity == ERROR
    assert finding.task_id == "b"
    assert finding.ref == "ghost.output"
    assert "unknown task 'ghost'" in finding.message


def test_output_of_task_on_no_path_is_an_error():
    definition = load(
        """
name: never
tasks:
  start: {name: S, action: ok}
  taken: {name: T, action: ok}
  never: {name: N, action: ok}
  after:
    name: After
    action: ok
    properties: {prompt: "{{never.output}}"}
routings:
  - {from: start, to: taken, condition: route_name, name: "yes"}
  - {from: taken, to: after}
  - {from: start, to: never, condition: route_name, name: "no"}
"""
    )

    (finding,) = validate_contracts(definition)

    assert finding.severity == ERROR
    assert finding.task_id == "after"
    assert finding.ref == "never.output"
    assert "no path runs 'never' before 'after'" in finding.message


def test_output_after_downstream_task_is_an_error():
    definition = load(LINEAR.replace("{{a.output}}", "{{c.output}}") + "")
    assert [f.severity for f in validate_contracts(definition)] == [ERROR]  # c unknown

    later = load(
        """
name: later
tasks:
  a: {name: A, action: ok, properties: {prompt: "{{b.output}}"}}
  b: {name: B, action: ok}
routings:
  - {from: a, to: b}
"""
    )
    (finding,) = validate_contracts(later)
    assert finding.severity == ERROR and finding.ref == "b.output"


def test_branch_output_used_after_plain_merge_is_a_warning():
    definition = load(BRANCHES % ("false", "false", "false"))

    (finding,) = validate_contracts(definition)

    assert finding.severity == WARNING
    assert finding.task_id == "merge"
    assert "only some paths" in finding.message


def test_synchronized_join_of_all_branches_is_clean():
    definition = load(BRANCHES % ("true", "true", "true"))

    assert validate_contracts(definition) == []


def test_output_produced_on_every_path_is_clean():
    definition = load(
        """
name: both
tasks:
  start: {name: S, action: ok}
  x: {name: X, action: ok}
  y: {name: Y, action: ok}
  end:
    name: End
    action: ok
    properties: {prompt: "{{start.output}}"}
routings:
  - {from: start, to: x, condition: route_name, name: a}
  - {from: start, to: y, condition: route_name, name: b}
  - {from: x, to: end}
  - {from: y, to: end}
"""
    )

    assert validate_contracts(definition) == []


def test_loop_output_is_available_on_second_pass_but_only_sometimes():
    definition = load(
        """
name: loop
tasks:
  work: {name: W, action: ok, properties: {prompt: "{{check.output}}"}}
  check: {name: C, action: ok}
routings:
  - {from: work, to: check}
  - {from: check, to: work, condition: route_name, name: again}
"""
    )

    (finding,) = validate_contracts(definition)

    assert finding.severity == WARNING


def test_property_key_written_by_a_task_is_not_an_unknown_task():
    definition = load(
        """
name: keyed
tasks:
  run: {name: R, action: ok, properties: {output_key: result}}
  use: {name: U, action: ok, properties: {prompt: "{{result.output}} {{result.success}}"}}
routings:
  - {from: run, to: use}
"""
    )

    assert validate_contracts(definition) == []


def test_undeclared_plain_property_is_only_a_warning():
    definition = load(LINEAR.replace("{{goal}}", "{{typo_key}}"))

    (finding,) = validate_contracts(definition)

    assert finding.severity == WARNING
    assert finding.ref == "typo_key"


def test_declared_and_runtime_properties_are_clean():
    text = LINEAR.replace("{{goal}}", "{{topic}} {{__total_cost__}}").replace(
        "tasks:", "properties: {topic: x}\ntasks:", 1
    )

    assert validate_contracts(load(text)) == []


class TestOutputSchema:
    def test_valid_nested(self):
        schema = {
            "type": "object",
            "required": ["items"],
            "properties": {"items": {"type": "array", "items": {"type": "integer"}}},
        }
        assert validate_output_schema(schema, {"items": [1, 2]}) == []

    def test_reports_path_of_each_violation(self):
        schema = {
            "type": "object",
            "required": ["a"],
            "properties": {"items": {"type": "array", "items": {"type": "integer"}}},
        }
        errors = validate_output_schema(schema, {"items": [1, "x"]})
        assert "$: missing required key 'a'" in errors
        assert "$.items[1]: expected integer, got str" in errors

    def test_bool_is_not_a_number(self):
        assert validate_output_schema({"type": "number"}, True)

    def test_wrong_top_level_type(self):
        assert validate_output_schema({"type": "object"}, "text") == ["$: expected object, got str"]


class OkAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.ok(output="done")


class TemplateAction(TaskAction):
    """Resolves the task's ``prompt`` and stores it."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.ok(output=context.resolve_template(task.properties["prompt"]))


MISSING = """
name: missing
%s
tasks:
  a: {name: A, action: template, properties: {prompt: "x{{typo_key}}y {{typo_key}}"}}
  b: {name: B, action: ok}
routings:
  - {from: a, to: b}
"""


@pytest.fixture
def engine():
    registry = ActionRegistry()
    registry.register_action("ok", OkAction)
    registry.register_action("template", TemplateAction)
    return WorkflowEngine(InMemoryStore(), registry)


async def run(engine, yaml_text: str, properties: dict | None = None):
    process = await engine.create_process(load(yaml_text), properties)
    await engine.start_process(process.id)
    return await engine.store.load_process(process.id)


async def test_unresolved_template_is_recorded_not_silent(engine):
    process = await run(engine, MISSING % "")

    assert process.state == ProcessState.COMPLETE
    assert process.properties["__task_output_a"] == "xy "
    assert process.properties["__contract_violations__"] == [{"task": "a", "ref": "typo_key"}]


async def test_resolved_template_records_nothing(engine):
    text = MISSING % ""

    process = await run(engine, text, {"typo_key": "v"})

    assert process.properties["__task_output_a"] == "xvy v"
    assert "__contract_violations__" not in process.properties


async def test_strict_templates_fails_the_task_naming_the_reference(engine):
    process = await run(engine, MISSING % "properties: {strict_templates: true}")

    assert process.state == ProcessState.FAILED
    tasks = await engine.store.load_tasks_for_process(process.id)
    failed = [t for t in tasks if t.error and "{{typo_key}}" in t.error]
    assert failed, [t.error for t in tasks]
