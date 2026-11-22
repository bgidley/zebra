"""The python_exec sandbox contract: defined once, enforced at run time (#323)."""

import builtins
import sys
from types import SimpleNamespace

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskState
from zebra.definitions.loader import load_definition_from_dict
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry

from zebra_tasks.compute import sandbox
from zebra_tasks.compute.python_exec import PythonExecAction
from zebra_tasks.compute.sandbox import (
    ALLOWED_MODULES,
    BLOCKED_BUILTINS,
    PRELOADED,
    SandboxImportError,
    build_globals,
    check_code,
    check_task_code,
    describe_contract,
    is_import_allowed,
)


def _context(properties: dict | None = None):
    process = SimpleNamespace(properties=dict(properties or {}))
    context = SimpleNamespace(process=process, extras={})
    context.resolve_template = lambda text: text
    context.set_process_property = process.properties.__setitem__
    return context


async def _run(code: str, properties: dict | None = None):
    context = _context(properties)
    task = SimpleNamespace(properties={"code": code})
    result = await PythonExecAction().run(task, context)
    return result, context


class TestSingleDefinition:
    def test_action_aliases_the_contract(self):
        assert PythonExecAction.ALLOWED_MODULES is ALLOWED_MODULES
        assert PythonExecAction.BLOCKED_BUILTINS is BLOCKED_BUILTINS

    def test_preloaded_names_come_from_the_contract(self):
        namespace = build_globals({})
        for name in PRELOADED:
            assert namespace[name] is sys.modules[name]
            assert name in ALLOWED_MODULES
        extras = set(namespace) - set(PRELOADED) - {"__builtins__", "props"}
        assert extras == set()


class TestImportGate:
    @pytest.mark.parametrize("module", sorted(ALLOWED_MODULES))
    async def test_every_allowed_top_level_module_imports(self, module):
        result, _ = await _run(f"import {module}\nresult = {module}.__name__")
        assert result.success, result.error
        assert result.output["result"] == module

    @pytest.mark.parametrize("module", ["os", "sys", "subprocess", "socket", "pathlib", "ast"])
    async def test_representative_denials(self, module):
        result, _ = await _run(f"import {module}")
        assert not result.success
        assert f"Module '{module}' is not allowed" in result.error

    async def test_from_import_and_submodule_follow_top_level_name(self):
        ok, _ = await _run("from os import path")
        assert not ok.success
        sub, _ = await _run("import collections.abc\nresult = 1")
        assert sub.success
        rel, _ = await _run("from . import x")
        assert not rel.success

    def test_import_gate_function(self):
        assert is_import_allowed("json") and is_import_allowed("collections.abc")
        assert not is_import_allowed("os") and not is_import_allowed("")

    def test_restricted_import_hook_is_reinstalled(self):
        safe = build_globals({})["__builtins__"]
        assert safe["__import__"] is not builtins.__import__
        assert safe["__import__"]("json").__name__ == "json"
        with pytest.raises(SandboxImportError, match="'os' is not allowed"):
            safe["__import__"]("os")

    async def test_dunder_import_goes_through_the_hook(self):
        ok, _ = await _run("result = __import__('json').__name__")
        assert ok.success and ok.output["result"] == "json"
        denied, _ = await _run("__import__('os')")
        assert not denied.success and "Module 'os' is not allowed" in denied.error


class TestBuiltinsAndNamespace:
    @pytest.mark.parametrize("name", sorted(BLOCKED_BUILTINS - {"__import__"}))
    def test_blocked_builtins_absent(self, name):
        assert name not in build_globals({})["__builtins__"]

    async def test_blocked_builtin_call_fails(self):
        result, _ = await _run("open('x')")
        assert not result.success and "NameError" in result.error

    async def test_props_filters_engine_keys(self):
        result, _ = await _run(
            "result = sorted(props)", {"a": 1, "__task_output_x": 2, "__total_cost__": 3}
        )
        assert result.output["result"] == ["a"]

    async def test_result_is_published_with_stdout(self):
        result, context = await _run("print('hi')\nresult = {'n': 1}")
        assert result.success
        assert result.output == {"result": {"n": 1}, "stdout": "hi\n", "stderr": ""}
        assert context.process.properties["result"] == {"n": 1}
        assert context.process.properties["result_stdout"] == "hi\n"

    async def test_preloaded_module_usable_without_import(self):
        result, _ = await _run("result = math.floor(json.loads('2.5'))")
        assert result.output["result"] == 2


class TestCheckCode:
    def test_clean_code(self):
        assert check_code("import json\nfrom collections import abc\nresult = json.dumps(1)") == []

    def test_rejected_imports_name_the_module(self):
        assert check_code("import os") == ["import of module 'os' is not allowed"]
        assert check_code("import os.path, json") == ["import of module 'os.path' is not allowed"]
        assert check_code("from subprocess import run") == [
            "import of module 'subprocess' is not allowed"
        ]
        assert check_code("from . import x") == ["import of module '.' is not allowed"]
        assert check_code("__import__('socket')") == ["import of module 'socket' is not allowed"]

    def test_blocked_builtin_calls_name_the_builtin(self):
        assert check_code("open('f')") == ["use of blocked builtin 'open'"]
        assert check_code("x = eval('1')") == ["use of blocked builtin 'eval'"]

    def test_rebound_name_is_not_flagged(self):
        assert check_code("def open(p):\n    return p\nresult = open(1)") == []
        assert check_code("input = 3\nresult = input") == []

    def test_dynamic_import_name_and_syntax_error_are_left_to_runtime(self):
        assert check_code("__import__(name)") == []
        assert check_code("def (") == []

    def test_templated_code_is_skipped_not_checked(self):
        assert check_task_code("import os\n{{code}}") is None
        assert check_task_code("import os") == ["import of module 'os' is not allowed"]
        assert check_task_code("d = {'a': {1}}") == []

    @pytest.mark.parametrize(
        "code",
        [
            "import os",
            "import json\nimport sys",
            "from os import path",
            "import collections.abc",
            "from . import x",
            "__import__('os')",
            "result = 1",
        ],
    )
    async def test_static_check_agrees_with_runtime_import_gate(self, code):
        result, _ = await _run(code)
        denied_at_runtime = not result.success and "is not allowed" in result.error
        assert bool(check_code(code)) == denied_at_runtime


class TestDescribeContract:
    def test_names_every_module_and_the_result_rule(self):
        text = describe_contract()
        for name in ALLOWED_MODULES:
            assert name in text
        assert "`result`" in text and "`props`" in text
        for name in BLOCKED_BUILTINS - {"__import__"}:
            assert name in text


class TestFailureMessage:
    async def _failure(self, code: str) -> str:
        registry = ActionRegistry()
        registry.register_defaults()
        registry.register_action("python_exec", PythonExecAction)
        engine = WorkflowEngine(InMemoryStore(), registry)
        definition = load_definition_from_dict(
            {
                "name": "t",
                "first_task": "a",
                "tasks": {
                    "a": {
                        "name": "A",
                        "action": "python_exec",
                        "properties": {"code": "{{code}}"},
                    }
                },
                "routings": [],
            }
        )
        process = await engine.create_process(definition, properties={"code": code})
        await engine.start_process(process.id)
        assert (await engine.store.load_process(process.id)).state == ProcessState.FAILED
        [task] = await engine.store.load_tasks_for_process(process.id)
        assert task.state == TaskState.FAILED
        return task.error

    async def test_denied_import_in_rendered_code_carries_cause_and_contract(self):
        error = await self._failure("import os\nresult = 1")
        assert "Module 'os' is not allowed" in error
        assert describe_contract() in error

    async def test_blocked_call_in_rendered_code_carries_cause_and_contract(self):
        error = await self._failure("open('x')")
        assert "NameError" in error and "'open'" in error
        assert describe_contract() in error

    async def test_ordinary_error_has_no_appendix(self):
        error = await self._failure("result = 1 / 0")
        assert "ZeroDivisionError" in error
        assert "Python sandbox rules" not in error

    async def test_unrelated_name_error_has_no_appendix(self):
        error = await self._failure("result = undefined_name")
        assert "NameError" in error
        assert "Python sandbox rules" not in error


def test_module_exports():
    assert sandbox.PRELOADED == ("math", "json", "datetime", "re", "random")
