"""Build Software workflow + BuilderWatcher, with the host builder faked (#98, #172).

Runs the real ``build_software.yaml`` through the engine. The host builder is played by the test:
it reads the job the workflow wrote into the spool and answers with result / published files,
exactly as ``scripts/zebra_builder.py`` does. The daemon's ``BuilderWatcher`` hands the answers
back to the parked workflow.
"""

import json
from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult, TaskState
from zebra.definitions.loader import load_definition, validate_definition
from zebra.forms import is_human_task
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.agent.propagate_failure import PropagateFailureAction
from zebra_tasks.builder.actions import ClaudeCodeBuildAction, PublishBuildAction
from zebra_tasks.builder.spool import BuilderSpool
from zebra_tasks.llm.action import LLMCallAction
from zebra_tasks.llm.base import LLMProvider, LLMResponse, TokenUsage
from zebra_tasks.llm.client import set_llm_factory

from zebra_agent.human_tasks import find_pending_human_task
from zebra_agent.scheduler.builder_watch import VIOLATIONS_KEY, BuilderWatcher

WORKFLOW = Path(__file__).parent.parent / "workflows" / "build_software.yaml"
BRIEF = {
    "title": "Add hello()",
    "prompt": "Add a hello() function.\n1. hello() returns 'hi'\n2. a test covers it",
    "repo": "gidley/zebra",
    "base_branch": "master",
    "test_command": "uv run pytest -q",
    "max_turns": 40,
    "minutes": 20,
}


class ScriptedModel(LLMProvider):
    """Answers the brief step with BRIEF and the report step with a sentence."""

    def __init__(self):
        self.prompts: list[str] = []

    async def complete(self, messages, tools=None, temperature=0.7, max_tokens=4096, **kw):
        text = "\n".join(str(m.content) for m in messages)
        self.prompts.append(text)
        content = json.dumps(BRIEF) if "brief for Claude Code" in text else "Your build ended."
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


class FakeHostBuilder:
    """Plays scripts/zebra_builder.py: answers jobs in the spool."""

    def __init__(self, root: Path):
        self.root = root

    def only_job(self) -> tuple[str, dict]:
        [job_dir] = [p for p in self.root.iterdir() if p.is_dir()]
        return job_dir.name, json.loads((job_dir / "job.json").read_text())

    def finish(self, state: str = "done", **extra) -> str:
        job_id, _ = self.only_job()
        result = {
            "job_id": job_id, "state": state, "summary": "Added hello() and a test.",
            "diffstat": " hello.py | 3 +++", "sensitive_files": [], "patch_excerpt": "+def hello",
            "patch_sha256": "f" * 64, "test": {"command": "uv run pytest -q", "rc": 0,
            "log_tail": "1 passed"}, "turns": 9, "notional_cost_usd": 0.8, "duration_s": 300,
            "violations": [],
        }  # fmt: skip
        result.update(extra)
        (self.root / job_id / "result.json").write_text(json.dumps(result))
        return job_id

    def publish_request(self) -> dict | None:
        job_id, _ = self.only_job()
        path = self.root / job_id / "publish.json"
        return json.loads(path.read_text()) if path.exists() else None

    def published(self, **answer) -> None:
        job_id, _ = self.only_job()
        answer = answer or {
            "branch": f"zebra-build/{job_id[:12]}",
            "mr_url": "https://gitlab.com/gidley/zebra/-/merge_requests/7",
        }
        (self.root / job_id / "published.json").write_text(json.dumps(answer))


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
    registry.register_action("claude_code_build", ClaudeCodeBuildAction)
    registry.register_action("publish_build", PublishBuildAction)
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
    process = await engine.create_process(definition, properties={"goal": "Add a hello()"})
    await engine.start_process(process.id)
    return process.id


async def ready(engine, process_id: str) -> list[str]:
    return [
        t.task_definition_id
        for t in await engine.store.load_tasks_for_process(process_id)
        if t.state == TaskState.READY
    ]


async def complete(engine, process_id: str, task_def_id: str, output: dict, route: str):
    [task] = [
        t
        for t in await engine.store.load_tasks_for_process(process_id)
        if t.task_definition_id == task_def_id and t.state == TaskState.READY
    ]
    await engine.complete_task(task.id, TaskResult(success=True, output=output, next_route=route))


async def deliver(watcher) -> int:
    delivered = await watcher.tick()
    await watcher.drain()
    return delivered


async def approve_brief(engine, process_id: str, **overrides):
    await complete(engine, process_id, "confirm_brief", {**BRIEF, **overrides}, "build")


def test_workflow_is_valid():
    assert validate_definition(load_definition(WORKFLOW)) == []


async def test_waits_are_external_and_reviews_are_human():
    tasks = load_definition(WORKFLOW).tasks
    assert not is_human_task(tasks["await_build"])
    assert not is_human_task(tasks["await_publish"])
    assert is_human_task(tasks["confirm_brief"])
    assert is_human_task(tasks["review_build"])


async def test_happy_path_builds_reviews_and_publishes(engine, watcher, host):
    process_id = await start(engine)
    assert await ready(engine, process_id) == ["confirm_brief"]

    await approve_brief(engine, process_id, max_turns=30)
    job_id, job = host.only_job()
    assert job["budget"] == {"max_turns": 30, "minutes": 20}
    assert job["repo"] == "gidley/zebra" and job["process_id"] == process_id
    assert "hello() returns 'hi'" in job["prompt"]

    # Parked on the external wait: the goal hands off as for a human task, no timeout runs.
    assert await ready(engine, process_id) == ["await_build"]
    pending = await find_pending_human_task(engine, process_id)
    assert pending is not None and pending[1] == "Claude Code Is Building"
    assert await deliver(watcher) == 0  # builder still working

    host.finish()
    assert await deliver(watcher) == 1
    assert await ready(engine, process_id) == ["review_build"]

    await complete(engine, process_id, "review_build", {"notes": "LGTM"}, "approve")
    request = host.publish_request()
    assert request["patch_sha256"] == "f" * 64  # the patch the reviewer saw
    assert request["mr_title"] == "Add hello()"
    assert "LGTM" in request["mr_description"]
    assert await ready(engine, process_id) == ["await_publish"]

    host.published()
    await deliver(watcher)
    process = await engine.store.load_process(process_id)
    assert process.state == ProcessState.COMPLETE
    assert process.properties["answer"] == "Your build ended."
    assert process.properties["__task_output_await_publish"]["mr_url"].endswith("/7")


async def test_rejected_review_never_publishes(engine, watcher, host):
    process_id = await start(engine)
    await approve_brief(engine, process_id)
    host.finish()
    await deliver(watcher)
    await complete(engine, process_id, "review_build", {}, "reject")

    assert host.publish_request() is None
    process = await engine.store.load_process(process_id)
    assert process.state == ProcessState.COMPLETE


async def test_cancelled_brief_writes_no_job(engine, host, spool_dir):
    process_id = await start(engine)
    await complete(engine, process_id, "confirm_brief", BRIEF, "cancel")
    assert list(spool_dir.iterdir()) == []
    assert (await engine.store.load_process(process_id)).state == ProcessState.COMPLETE


@pytest.mark.parametrize("state", ["failed", "over_budget", "rejected", "cancelled"])
async def test_unfinished_build_fails_the_workflow(engine, watcher, host, state):
    process_id = await start(engine)
    await approve_brief(engine, process_id)
    host.finish(state, error=f"build {state}")
    await deliver(watcher)

    process = await engine.store.load_process(process_id)
    assert process.state == ProcessState.FAILED
    assert host.publish_request() is None
    failed = [
        t for t in await engine.store.load_tasks_for_process(process_id) if t.error is not None
    ]
    assert any(state in (t.error or "") for t in failed)


async def test_budget_breach_is_recorded_on_the_process(engine, watcher, host):
    process_id = await start(engine)
    await approve_brief(engine, process_id)
    violation = {"limit": "minutes", "used": 21.0, "allowed": 20}
    job_id = host.finish("over_budget", error="stopped after 20 minutes", violations=[violation])
    await deliver(watcher)

    process = await engine.store.load_process(process_id)
    [recorded] = process.properties[VIOLATIONS_KEY]
    assert recorded["job_id"] == job_id and recorded["limit"] == "minutes"


async def test_watcher_cancels_builds_of_ended_goals(engine, watcher, host, spool_dir):
    process_id = await start(engine)
    await approve_brief(engine, process_id)
    job_id, _ = host.only_job()

    await watcher.tick()
    assert not (spool_dir / job_id / "cancel").exists()  # goal still running

    await engine.fail_process(process_id, "cancelled by the user")
    await watcher.tick()
    assert (spool_dir / job_id / "cancel").exists()


async def test_watcher_leaves_human_tasks_alone(engine, watcher, host):
    process_id = await start(engine)
    assert await deliver(watcher) == 0
    assert await ready(engine, process_id) == ["confirm_brief"]


async def test_watcher_delivers_once(engine, watcher, host):
    process_id = await start(engine)
    await approve_brief(engine, process_id)
    host.finish()
    first = await watcher.tick()
    second = await watcher.tick()  # completion still in flight
    await watcher.drain()
    assert (first, second) == (1, 0)
    assert await ready(engine, process_id) == ["review_build"]
