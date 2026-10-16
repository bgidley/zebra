"""manage.py run_workflow: run a named workflow directly, or report its status (#190)."""

import json
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from zebra.core.engine import WorkflowEngine
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_agent.library import WorkflowLibrary
from zebra_agent_web.api import agent_engine
from zebra_tasks.agent.zebra_source import ZebraSourceAction

WORKFLOWS = Path(__file__).resolve().parents[3] / "zebra-agent" / "workflows"


@pytest.fixture
def engine(tmp_path, monkeypatch) -> WorkflowEngine:
    library = WorkflowLibrary(tmp_path / "workflows")
    library.copy_builtin_workflows(WORKFLOWS)
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("zebra_source", ZebraSourceAction)
    engine = WorkflowEngine(InMemoryStore(), registry, extras={"__workflow_library__": library})

    async def _noop():
        return None

    monkeypatch.delenv("ZEBRA_SOURCE_ROOT", raising=False)
    monkeypatch.setattr(agent_engine, "ensure_initialized", _noop)
    monkeypatch.setattr(agent_engine, "get_agent_loop", lambda: SimpleNamespace(engine=engine))
    monkeypatch.setattr(agent_engine, "get_library", lambda: library)
    monkeypatch.setattr(agent_engine, "get_llm_provider_name", lambda: "anthropic")
    return engine


def _call(*args) -> tuple[dict, int]:
    out = StringIO()
    try:
        call_command("run_workflow", *args, stdout=out)
        code = 0
    except SystemExit as e:
        code = e.code
    return json.loads(out.getvalue()), code


def test_runs_a_workflow_with_json_inputs(engine, tmp_path):
    inputs = tmp_path / "in.json"
    inputs.write_text(json.dumps({"path": "pyproject.toml", "start_line": 1, "end_line": 1}))

    result, code = _call("Read Zebra Source", "--input-file", str(inputs))

    assert code == 0
    assert result["status"] == "complete"
    assert result["output"].startswith("    1| ")
    assert result["run_id"]

    status, code = _call("--status", result["process_id"])
    assert code == 0
    assert status["status"] == "complete"


def test_unknown_workflow_fails(engine):
    result, code = _call("No Such Workflow")

    assert code == 1
    assert result["status"] == "failed"
    assert "No workflow" in result["error"]


def test_missing_required_input_fails(engine):
    result, code = _call("Read Zebra Source")

    assert code == 1
    assert "path" in result["error"]


def test_status_of_unknown_process_fails(engine):
    result, code = _call("--status", "nope")

    assert code == 1
    assert result["status"] == "failed"
