"""python_exec sandbox contract: prompt wiring, save-time check, shipped workflows (#323)."""

from pathlib import Path

import pytest
import yaml
import zebra
from zebra.core.engine import WorkflowEngine
from zebra.definitions.loader import load_definition, load_definition_from_dict
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.compute.sandbox import ALLOWED_MODULES, check_task_code, describe_contract

import zebra_agent
from zebra_agent.library import WorkflowContractError, WorkflowLibrary
from zebra_agent.loop import AgentLoop

AGENT_WORKFLOWS = Path(zebra_agent.__file__).parent.parent / "workflows"
PY_TEMPLATES = Path(zebra.__file__).parent / "templates"
COMPUTE = AGENT_WORKFLOWS / "compute.yaml"


def render_planner_prompt(engine: WorkflowEngine) -> str:
    """The Compute planner's system prompt, resolved the way the llm_call action resolves it."""
    definition = load_definition(COMPUTE)
    process = type("P", (), {"properties": {"goal": "add 1 and 2"}})()
    task_def = definition.tasks["plan"]
    context = ExecutionContext(
        engine=engine,
        store=engine.store,
        process=process,
        process_definition=definition,
        task_definition=task_def,
        extras=engine.extras,
    )
    return context.resolve_template(task_def.properties["system_prompt"])


def assert_is_contract(prompt: str) -> None:
    contract = describe_contract()
    assert contract in prompt
    assert "{{python_sandbox}}" not in prompt
    for name in ALLOWED_MODULES:
        assert name in prompt
    assert "Assign the final value to a variable named `result`" in prompt


class TestPromptThroughEngineFactories:
    def test_agent_loop_factory(self):
        registry = ActionRegistry()
        engine = WorkflowEngine(InMemoryStore(), registry)
        assert "__python_sandbox__" not in engine.extras
        AgentLoop(library=None, engine=engine, metrics=None)

        assert_is_contract(render_planner_prompt(engine))

    def test_engine_without_extra_leaves_the_token_unresolved(self):
        engine = WorkflowEngine(InMemoryStore(), ActionRegistry())
        prompt = render_planner_prompt(engine)
        assert describe_contract() not in prompt

    def test_compute_prompt_no_longer_lists_modules_by_hand(self):
        text = COMPUTE.read_text()
        assert "Available modules:" not in text
        assert "{{python_sandbox}}" in text


WORKFLOW = """name: "Sandbox Probe"
first_task: a
tasks:
  a:
    name: A
    action: python_exec
    properties:
      code: |
{code}
routings: []
"""


def workflow_with(code: str) -> str:
    return WORKFLOW.format(code="\n".join("        " + line for line in code.splitlines()))


class TestSaveTimeCheck:
    @pytest.fixture
    def lib(self, tmp_path):
        return WorkflowLibrary(tmp_path / "workflows")

    @pytest.mark.parametrize(
        ("code", "symbol"),
        [
            ("import os\nresult = 1", "os"),
            ("from subprocess import run", "subprocess"),
            ("result = 1\n__import__('socket')", "socket"),
        ],
    )
    def test_rejected_import_names_task_and_module(self, lib, code, symbol):
        with pytest.raises(WorkflowContractError) as err:
            lib.save(workflow_with(code), writer="human")
        assert f"task 'a' python_exec: import of module '{symbol}' is not allowed" in str(err.value)
        assert list(lib.library_path.rglob("*.yaml")) == []

    @pytest.mark.parametrize("builtin", ["open", "eval", "exec", "compile", "input", "breakpoint"])
    def test_blocked_call_names_task_and_builtin(self, lib, builtin):
        with pytest.raises(WorkflowContractError) as err:
            lib.save(workflow_with(f"{builtin}('x')"), writer="human")
        assert f"task 'a' python_exec: use of blocked builtin '{builtin}'" in str(err.value)

    def test_allowed_code_saves(self, lib):
        assert lib.save(
            workflow_with("import json\nresult = json.dumps(1)"), writer="human"
        ).exists()

    def test_templated_code_is_not_rejected(self, lib):
        assert lib.save(workflow_with("{{code}}"), writer="human").exists()
        assert lib.save(
            workflow_with("import os\n{{code}}").replace("Probe", "Probe2"), writer="human"
        ).exists()

    def test_rejected_update_leaves_stored_definition_unchanged(self, lib):
        path = lib.save(workflow_with("result = 1"), writer="human")
        before = path.read_text()
        with pytest.raises(WorkflowContractError):
            lib.save(workflow_with("import os"), writer="human")
        assert path.read_text() == before
        assert list(lib.library_path.rglob("*.yaml")) == [path]


def _python_exec_tasks(path: Path) -> list[tuple[str, str]]:
    definition = load_definition_from_dict(yaml.safe_load(path.read_text()), source=str(path))
    return [
        (task_id, task.properties["code"])
        for task_id, task in definition.tasks.items()
        if task.action == "python_exec" and isinstance(task.properties.get("code"), str)
    ]


INVENTORIES = {"zebra-agent/workflows": AGENT_WORKFLOWS, "zebra-py/templates": PY_TEMPLATES}


class TestShippedWorkflows:
    @pytest.mark.parametrize("inventory", INVENTORIES)
    def test_inventory_is_discovered(self, inventory):
        assert sorted(INVENTORIES[inventory].glob("*.yaml"))

    def test_shipped_python_exec_code_honours_the_contract(self):
        checked, skipped = [], []
        for path in [p for d in INVENTORIES.values() for p in sorted(d.glob("*.yaml"))]:
            for task_id, code in _python_exec_tasks(path):
                findings = check_task_code(code)
                if findings is None:
                    skipped.append((path.name, task_id))
                else:
                    assert findings == [], (path.name, task_id)
                    checked.append((path.name, task_id))
        # Templated snippets (compute.yaml's "{{code}}") are skipped, not verified
        assert ("compute.yaml", "execute") in skipped
        assert ("compute.yaml", "execute") not in checked
