"""Improve Zebra workflow + BuilderWatcher, with the host builder faked (#251, slice B).

Runs the real ``improve_zebra.yaml`` through the engine. The test plays the host builder: it
reads each stage job the workflow writes into the spool and answers with a result, as
``scripts/zebra_builder.py`` does, and the daemon's ``BuilderWatcher`` hands it back.
"""

import json
from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult, TaskState
from zebra.definitions.loader import load_definition, validate_definition
from zebra.forms import is_human_task
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.agent.propagate_failure import PropagateFailureAction
from zebra_tasks.builder.actions import ClaudeCodeBuildAction
from zebra_tasks.builder.spool import BuilderSpool
from zebra_tasks.llm.action import LLMCallAction
from zebra_tasks.llm.agent import LLMAgentAction
from zebra_tasks.llm.base import LLMProvider, LLMResponse, TokenUsage
from zebra_tasks.llm.client import set_llm_factory

from zebra_agent.library import WorkflowLibrary, list_goal_workflows
from zebra_agent.scheduler.builder_watch import BuilderWatcher

WORKFLOWS = Path(__file__).parent.parent / "workflows"
WORKFLOW = WORKFLOWS / "improve_zebra.yaml"
BRANCH = "f251/improve-zebra"
OUTCOMES = "| # | Outcome | How we'll know |\n|---|---|---|\n| O1 | Builds | Tests |"
RECOMMENDATION = {
    "verdicts": [{"id": "O1", "verdict": "met", "evidence": "tests/test_x.py::test_y"}],
    "recommendation": "merge",
    "reasons": "Pipeline green and O1 met.",
    "markdown": "| O1 | met |\n\n**Recommendation: merge**",
}


class ScriptedModel(LLMProvider):
    """Answers each LLM step of the workflow by recognising its prompt."""

    def __init__(self):
        self.prompts: list[str] = []

    async def complete(self, messages, tools=None, temperature=0.7, max_tokens=4096, **kw):
        text = "\n".join(str(m.content) for m in messages)
        self.prompts.append(text)
        if "deciding whether a change" in text:
            content = json.dumps(RECOMMENDATION)
        elif "has been proposed with the outcomes" in text:
            content = "Outcomes fit the issue; O1 should name the test."
        else:
            content = "Zebra's change ended."
        return LLMResponse(
            content=content,
            tool_calls=None,
            finish_reason="end_turn",
            usage=TokenUsage(10, 10),
            model="test/model",
        )

    async def stream(self, *args, **kwargs):
        raise NotImplementedError
        yield ""

    @property
    def name(self) -> str:
        return "scripted"

    @property
    def model(self) -> str:
        return "test/model"

    @property
    def max_context_tokens(self) -> int:
        return 200_000

    def prompt_with(self, marker: str) -> str:
        [prompt] = [p for p in self.prompts if marker in p]
        return prompt


class FakeHostBuilder:
    """Plays scripts/zebra_builder.py for delivery stages."""

    def __init__(self, root: Path):
        self.root = root

    def jobs(self) -> list[tuple[str, dict]]:
        dirs = sorted(
            (p for p in self.root.iterdir() if p.is_dir()),
            key=lambda p: (p / "job.json").stat().st_mtime_ns,
        )
        return [(d.name, json.loads((d / "job.json").read_text())) for d in dirs]

    def open_job(self) -> tuple[str, dict]:
        [(job_id, job)] = [
            (i, j) for i, j in self.jobs() if not (self.root / i / "result.json").exists()
        ]
        return job_id, job

    def finish(self, state: str = "done", **extra) -> dict:
        job_id, job = self.open_job()
        result = {
            "job_id": job_id, "state": state, "stage": job["stage"], "branch": job["branch"],
            "issue": job["issue"], "summary": f"{job['stage']} finished.", "violations": [],
        }  # fmt: skip
        if job["stage"] == "propose":
            result["report"] = {"change": "improve-search", "outcomes_markdown": OUTCOMES}
        if job["stage"] == "ship":
            result.update(
                head_sha="b" * 40,
                changed_files=["scripts/x.sh", "zebra_tasks/a.py"],
                sensitive_files=["scripts/x.sh"],
                pipeline={"id": 9, "status": "success", "web_url": "https://ci/9"},
                diff_excerpt="--- a/zebra_tasks/a.py\n+++ b/zebra_tasks/a.py\n+def flag(): ...",
                diff_truncated=False,
                report={"pr_url": "https://github.com/bgidley/zebra/pull/12", "notes": "n/a"},
            )
        result.update(extra)
        (self.root / job_id / "result.json").write_text(json.dumps(result))
        return job


@pytest.fixture
def spool_dir(tmp_path) -> Path:
    path = tmp_path / "builds"
    path.mkdir()
    return path


@pytest.fixture
def host(spool_dir) -> FakeHostBuilder:
    return FakeHostBuilder(spool_dir)


@pytest.fixture
def engine(spool_dir) -> WorkflowEngine:
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("llm_call", LLMCallAction)
    registry.register_action("llm_agent", LLMAgentAction)
    registry.register_action("claude_code_build", ClaudeCodeBuildAction)
    registry.register_action("propagate_failure", PropagateFailureAction)
    return WorkflowEngine(
        InMemoryStore(), registry, extras={"__builder_spool__": BuilderSpool(spool_dir)}
    )


@pytest.fixture
def watcher(engine, spool_dir) -> BuilderWatcher:
    return BuilderWatcher(engine, BuilderSpool(spool_dir))


@pytest.fixture(autouse=True)
def model():
    scripted = ScriptedModel()
    set_llm_factory(lambda m: scripted)
    return scripted


async def start(engine) -> str:
    definition = load_definition(WORKFLOW)
    await engine.store.save_definition(definition)
    process = await engine.create_process(
        definition, properties={"issue": "251", "title": "Flag truncated search results"}
    )
    await engine.start_process(process.id)
    return process.id


async def ready(engine, process_id: str) -> list[str]:
    return [
        t.task_definition_id
        for t in await engine.store.load_tasks_for_process(process_id)
        if t.state == TaskState.READY
    ]


async def answer(watcher, host, state: str = "done", **extra) -> dict:
    job = host.finish(state, **extra)
    await watcher.tick()
    await watcher.drain()
    return job


async def review(engine, process_id: str, route: str, feedback: str = ""):
    [task] = [
        t
        for t in await engine.store.load_tasks_for_process(process_id)
        if t.task_definition_id == "review_pr" and t.state == TaskState.READY
    ]
    output = {"feedback": feedback}
    await engine.complete_task(task.id, TaskResult(success=True, output=output, next_route=route))


async def review_form(engine, process_id: str) -> dict[str, str]:
    """The review form's read-only fields, resolved against the process as the web UI does."""
    process = await engine.store.load_process(process_id)
    definition = await engine.store.load_definition(process.definition_id)
    task_def = definition.tasks["review_pr"]
    context = ExecutionContext(
        engine=engine,
        store=engine.store,
        process=process,
        process_definition=definition,
        task_definition=task_def,
        extras={},
    )
    fields = task_def.properties["schema"]["properties"]
    return {
        name: context.resolve_template(field["default"])
        for name, field in fields.items()
        if field.get("readOnly")
    }


async def to_review(engine, watcher, host) -> str:
    """Run a process up to the human PR review."""
    process_id = await start(engine)
    await answer(watcher, host)  # propose
    await answer(watcher, host)  # ship
    assert await ready(engine, process_id) == ["review_pr"]
    return process_id


def test_workflow_is_valid():
    assert validate_definition(load_definition(WORKFLOW)) == []


def test_waits_are_external_and_only_the_pr_review_needs_a_person():
    tasks = load_definition(WORKFLOW).tasks
    assert [t for t, d in tasks.items() if is_human_task(d)] == ["review_pr"]
    assert not is_human_task(tasks["await_propose"]) and not is_human_task(tasks["await_ship"])


async def test_it_is_internal_and_never_offered_for_a_goal(tmp_path):
    library = WorkflowLibrary(tmp_path / "workflows")
    library.copy_builtin_workflows(WORKFLOWS)
    [info] = [w for w in await library.list_workflows() if w.name == "Improve Zebra"]
    assert "system" in info.tags
    assert "Improve Zebra" not in {w["name"] for w in await list_goal_workflows(library)}


async def test_happy_path_reaches_the_pr_review_with_zebras_recommendation(
    engine, watcher, host, model
):
    process_id = await start(engine)

    # Propose: one job, on the issue's branch, parked on the external wait.
    _, propose = host.open_job()
    assert (propose["stage"], propose["issue"], propose["branch"]) == ("propose", 251, BRANCH)
    assert "Flag truncated search results" in propose["prompt"]
    assert await ready(engine, process_id) == ["await_propose"]

    await answer(watcher, host)
    feedback_prompt = model.prompt_with("has been proposed with the outcomes")
    assert OUTCOMES in feedback_prompt and "improve-search" in feedback_prompt

    # Ship: same branch, carries the change and Zebra's outcome feedback.
    _, ship = host.open_job()
    assert (ship["stage"], ship["branch"]) == ("ship", BRANCH)
    assert "improve-search" in ship["prompt"]
    assert "O1 should name the test" in ship["prompt"]

    await answer(watcher, host)
    recommend_prompt = model.prompt_with("deciding whether a change")
    for fact in ("success https://ci/9", "scripts/x.sh", "+def flag()", "pull/12", OUTCOMES):
        assert fact in recommend_prompt
    assert await ready(engine, process_id) == ["review_pr"]
    process = await engine.store.load_process(process_id)
    assert process.properties["recommendation"]["recommendation"] == "merge"
    shown = await review_form(engine, process_id)
    assert shown["pull_request"] == "https://github.com/bgidley/zebra/pull/12"
    assert shown["pipeline"] == "**success** https://ci/9"
    assert shown["sensitive"] == "['scripts/x.sh']"
    assert shown["recommendation"] == RECOMMENDATION["markdown"]
    assert shown["outcome_feedback"] == "Outcomes fit the issue; O1 should name the test."

    await review(engine, process_id, "merge", "Looks good")
    process = await engine.store.load_process(process_id)
    assert process.state == ProcessState.COMPLETE
    assert process.properties["answer"] == "Zebra's change ended."
    assert [j["stage"] for _, j in host.jobs()] == ["propose", "ship"]  # no merge stage yet


async def test_changes_loop_back_to_ship_on_the_same_branch(engine, watcher, host):
    process_id = await to_review(engine, watcher, host)

    await review(engine, process_id, "changes", "Rename flag() to mark_truncated()")
    _, again = host.open_job()
    assert (again["stage"], again["branch"]) == ("ship", BRANCH)
    assert "Rename flag() to mark_truncated()" in again["prompt"]

    await answer(watcher, host)
    assert await ready(engine, process_id) == ["review_pr"]  # reviewed again
    await review(engine, process_id, "merge")
    assert (await engine.store.load_process(process_id)).state == ProcessState.COMPLETE


async def test_reject_ends_without_another_stage(engine, watcher, host):
    process_id = await to_review(engine, watcher, host)

    await review(engine, process_id, "reject", "Wrong approach")
    process = await engine.store.load_process(process_id)
    assert process.state == ProcessState.COMPLETE
    assert len(host.jobs()) == 2


@pytest.mark.parametrize("stage", ["propose", "ship"])
@pytest.mark.parametrize("state", ["failed", "over_budget", "rejected", "cancelled"])
async def test_a_stage_that_does_not_finish_fails_the_workflow(engine, watcher, host, stage, state):
    process_id = await start(engine)
    if stage == "ship":
        await answer(watcher, host)
    await answer(watcher, host, state, error=f"{stage} went {state}")

    process = await engine.store.load_process(process_id)
    assert process.state == ProcessState.FAILED
    failed = [t for t in await engine.store.load_tasks_for_process(process_id) if t.error]
    assert any(f"{stage} went {state}" in (t.error or "") for t in failed)
