"""Golden tasks and gym scores (#171)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from zebra.definitions.loader import load_definition

from zebra_agent.gym import (
    DEFAULT_GOLDEN_DIR,
    GOLDEN_DIR_ENV,
    golden_dir,
    load_golden_tasks,
)
from zebra_agent.library import WorkflowLibrary
from zebra_agent.metrics import GymScore
from zebra_agent.storage.metrics import InMemoryMetricsStore

_WORKFLOWS = Path(__file__).parents[1] / "workflows"

VALID = """id: {id}
workflow: "Answer Question"
goal: "What is 2 + 2?"
expected: "4"
criteria: ["Says 4"]
"""


def test_loads_valid_and_skips_invalid(tmp_path):
    (tmp_path / "b.yaml").write_text(VALID.format(id="b"))
    (tmp_path / "a.yaml").write_text(VALID.format(id="a"))
    (tmp_path / "no_criteria.yaml").write_text(VALID.format(id="c").replace('["Says 4"]', "[]"))
    (tmp_path / "missing_goal.yaml").write_text("id: d\nworkflow: X\nexpected: y\ncriteria: [z]\n")
    (tmp_path / "broken.yaml").write_text("id: [unclosed")
    (tmp_path / "duplicate.yaml").write_text(VALID.format(id="a"))

    tasks = load_golden_tasks(tmp_path)

    assert [t.id for t in tasks] == ["a", "b"]
    assert tasks[0].criteria == ["Says 4"]
    assert tasks[0].to_dict()["workflow"] == "Answer Question"


def test_missing_directory_is_empty(tmp_path):
    assert load_golden_tasks(tmp_path / "nope") == []


def test_env_overrides_directory(tmp_path, monkeypatch):
    monkeypatch.setenv(GOLDEN_DIR_ENV, str(tmp_path))
    assert golden_dir() == tmp_path
    monkeypatch.delenv(GOLDEN_DIR_ENV)
    assert golden_dir() == DEFAULT_GOLDEN_DIR


def test_library_filters_by_workflow(tmp_path):
    golden = tmp_path / "golden"
    golden.mkdir()
    (golden / "a.yaml").write_text(VALID.format(id="a"))
    (golden / "b.yaml").write_text(VALID.format(id="b").replace("Answer Question", "Other"))
    library = WorkflowLibrary(tmp_path / "lib", golden_path=golden)

    assert [t.id for t in library.list_golden_tasks()] == ["a", "b"]
    assert [t.id for t in library.list_golden_tasks("Other")] == ["b"]


def test_shipped_golden_tasks_target_runnable_builtin_workflows():
    """Every built-in golden task is valid and names a fully automatic built-in workflow."""
    files = sorted(DEFAULT_GOLDEN_DIR.glob("*.yaml"))
    tasks = load_golden_tasks()
    assert files and len(tasks) == len(files)

    builtin = {}
    for path in _WORKFLOWS.glob("*.yaml"):
        data = yaml.safe_load(path.read_text())
        builtin[data["name"]] = (path, data.get("tags") or [])
    for task in tasks:
        assert task.workflow in builtin, task.id
        path, tags = builtin[task.workflow]
        definition = load_definition(path)
        assert all(t.auto for t in definition.tasks.values()), task.workflow
        assert "system" not in tags, task.workflow


async def test_in_memory_gym_scores_filter_and_order():
    store = InMemoryMetricsStore()
    now = datetime.now(UTC)
    old = GymScore.create("run1", "a", "Answer Question", "current", 0.5)
    old.created_at = now - timedelta(days=1)
    new = GymScore.create("run2", "a", "Answer Question", "candidate", 1.0, details={"x": 1})
    new.created_at = now - timedelta(hours=1)
    other = GymScore.create("run2", "b", "Other", "current", None, error="judge failed")
    other.created_at = now
    await store.record_gym_scores([old, new, other])

    assert [s.id for s in await store.get_gym_scores()] == [other.id, new.id, old.id]
    assert [s.id for s in await store.get_gym_scores(golden_id="a")] == [new.id, old.id]
    assert [s.id for s in await store.get_gym_scores(variant="current")][-1] == old.id
    assert [s.id for s in await store.get_gym_scores(workflow_name="Other")] == [other.id]
    assert len(await store.get_gym_scores(limit=1)) == 1
