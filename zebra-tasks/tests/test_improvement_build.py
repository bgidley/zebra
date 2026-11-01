"""Tests for StartImprovementBuildAction — "build" requests start Improve Zebra (#251)."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_agent.library import WorkflowLibrary

from zebra_tasks.agent.improvements import (
    BUILD_WORKFLOW,
    REQUEST_WORKFLOW,
    FileImprovementIssueAction,
    StartImprovementBuildAction,
    issue_iid,
    render_markdown,
)
from zebra_tasks.builder.actions import ClaudeCodeBuildAction
from zebra_tasks.builder.spool import BuilderSpool

BUILTIN = Path(__file__).parents[2] / "zebra-agent" / "workflows"
MODULE = "zebra_tasks.agent.improvements"
_RealAsyncClient = httpx.AsyncClient

IMPROVEMENT = {
    "title": "Flag truncated results in Search Zebra Source",
    "area": "task_action",
    "problem": "Search results are cut without saying so.",
    "evidence": "Postmortem lesson",
    "suggested_change": "Say when results were truncated.",
    "impact": "medium",
}


def gitlab_client(status_code: int = 201):
    """An httpx client factory answering GitLab's issue search and create."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=[])
        if status_code != 201:
            return httpx.Response(status_code, json={"message": "nope"})
        return httpx.Response(
            201, json={"iid": 42, "web_url": "https://gitlab.com/gidley/zebra/-/issues/42"}
        )

    return lambda **kw: _RealAsyncClient(transport=httpx.MockTransport(handler), **kw)


@pytest.fixture(autouse=True)
def gitlab_env(monkeypatch):
    monkeypatch.setenv("ZEBRA_GITLAB_TOKEN", "glpat-secret")


@pytest.fixture
def library(tmp_path):
    lib = WorkflowLibrary(tmp_path / "workflows")
    lib.copy_builtin_workflows(BUILTIN)
    return lib


@pytest.fixture
def spool(tmp_path) -> BuilderSpool:
    (tmp_path / "builds").mkdir()
    return BuilderSpool(tmp_path / "builds")


@pytest.fixture
def engine(library, spool):
    registry = ActionRegistry()
    registry.register_action("file_improvement_issue", FileImprovementIssueAction)
    registry.register_action("start_improvement_build", StartImprovementBuildAction)
    registry.register_action("claude_code_build", ClaudeCodeBuildAction)
    return WorkflowEngine(
        InMemoryStore(),
        registry,
        extras={"__workflow_library__": library, "__builder_spool__": spool},
    )


async def review(engine, library, status_code: int = 201, **verdict):
    """Run a Zebra Improvement Request through its review with *verdict*."""
    process = await engine.create_process(
        library.get_workflow(REQUEST_WORKFLOW),
        properties={
            "improvement": IMPROVEMENT,
            "improvement_title": IMPROVEMENT["title"],
            "improvement_markdown": render_markdown(IMPROVEMENT),
            "source_process_id": "dream-1",
            "__user_id__": 7,
        },
    )
    await engine.start_process(process.id)
    [task] = await engine.store.load_tasks_for_process(process.id)
    with patch(f"{MODULE}.httpx.AsyncClient", gitlab_client(status_code)):
        await engine.complete_task(task.id, TaskResult.ok(output=verdict))
    return await engine.store.load_process(process.id)


def spool_jobs(spool: BuilderSpool) -> list[dict]:
    return [json.loads((d / "job.json").read_text()) for d in spool.root.iterdir() if d.is_dir()]


async def test_build_verdict_files_the_issue_and_starts_improve_zebra(engine, library, spool):
    process = await review(engine, library, verdict="build")

    assert process.state == ProcessState.COMPLETE
    assert process.properties["filed_issue"]["iid"] == 42
    started = process.properties["improvement_build"]
    assert started["issue"] == 42
    build = await engine.store.load_process(started["process_id"])
    definition = await engine.store.load_definition(build.definition_id)
    assert definition.name == BUILD_WORKFLOW
    assert build.state == ProcessState.RUNNING  # parked on the propose stage
    assert build.properties["issue"] == "42"
    assert build.properties["title"] == IMPROVEMENT["title"]
    assert build.properties["source_process_id"] == process.id
    assert build.properties["__user_id__"] == 7
    [job] = spool_jobs(spool)
    assert (job["stage"], job["issue"], job["branch"]) == ("propose", 42, "f42/improve-zebra")
    assert job["process_id"] == build.id


async def test_build_with_a_linked_issue_builds_that_issue(engine, library, spool):
    link = "https://gitlab.com/gidley/zebra/-/work_items/77"
    process = await review(engine, library, verdict="build", issue_url=link)

    assert process.properties["filed_issue"] == {"skipped": "reviewer linked an issue"}
    assert process.properties["improvement_build"]["issue"] == 77
    [job] = spool_jobs(spool)
    assert job["issue"] == 77


@pytest.mark.parametrize("verdict", ["accepted", "rejected", "duplicate", "later"])
async def test_other_verdicts_start_nothing(engine, library, spool, verdict):
    process = await review(engine, library, verdict=verdict)

    assert process.state == ProcessState.COMPLETE
    assert process.properties["improvement_build"] == {"skipped": "not chosen for building"}
    assert spool_jobs(spool) == []


async def test_failed_filing_without_a_link_records_an_error(engine, library, spool):
    process = await review(engine, library, status_code=500, verdict="build")

    assert process.state == ProcessState.COMPLETE  # never fails the request
    assert "error" in process.properties["filed_issue"]
    assert "no GitLab issue" in process.properties["improvement_build"]["error"]
    assert spool_jobs(spool) == []


async def test_a_rerun_does_not_start_a_second_build(library):
    started = {"process_id": "p-1", "issue": 42}
    context = SimpleNamespace(
        process=SimpleNamespace(
            id="req-1",
            properties={"__task_output_review": {"verdict": "build"}, "improvement_build": started},
        ),
        extras={"__workflow_library__": library},
        set_process_property=lambda key, value: None,
    )
    task = SimpleNamespace(properties={})
    result = await StartImprovementBuildAction().run(task, context)
    assert result.output == {**started, "skipped": "already started"}


@pytest.mark.parametrize(
    ("properties", "expected"),
    [
        ({"filed_issue": {"iid": 42}}, 42),
        ({"__task_output_review": {"issue_url": "https://gitlab.com/g/z/-/issues/9"}}, 9),
        ({"__task_output_review": {"issue_url": "https://gitlab.com/g/z/-/work_items/9#x"}}, 9),
        ({"__task_output_review": {"issue_url": "https://example.com/nothing"}}, None),
        ({"filed_issue": {"error": "boom"}}, None),
    ],
)
def test_issue_iid(properties, expected):
    assert issue_iid(properties) == expected
