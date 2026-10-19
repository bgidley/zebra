"""Golden gym: score workflows on golden tasks and gate self-modifications (#171).

Uses a real engine + InMemoryStore, so the children, the suspend and the resume
come from the engine. Only the LLM judge is faked: it scores an output 1 when it
mentions Canberra and 0 otherwise.
"""

import asyncio
from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskInstance, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_agent.library import WorkflowLibrary
from zebra_agent.storage.metrics import InMemoryMetricsStore

from zebra_tasks.agent import gym as gym_module
from zebra_tasks.agent.gym import RunGoldenGymAction, unsafe_reason
from zebra_tasks.agent.optimizer import WorkflowOptimizerAction
from zebra_tasks.llm.base import LLMResponse, TokenUsage


class _AnswerAction(TaskAction):
    """Write the task's ``text`` as the workflow's answer, with a small cost."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        context.set_process_property("answer", task.properties.get("text", ""))
        context.set_process_property("__total_cost__", 0.01)
        return TaskResult.ok()


class _BrokenAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.fail("workflow broke")


class _SlowAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        await asyncio.sleep(5)
        context.set_process_property("answer", "Canberra")
        return TaskResult.ok()


class _EmailAction(TaskAction):
    reversibility_hint = "always_irreversible"

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        raise AssertionError("the gym must never run an irreversible action")


class _FakeJudge:
    """Score every criterion 1 if the output mentions Canberra, else 0."""

    model = "fake-judge"

    def __init__(self, reply: str | None = None):
        self.reply = reply
        self.calls = 0

    async def complete(self, messages, **kwargs) -> LLMResponse:
        self.calls += 1
        prompt = messages[-1].content
        output = prompt.split("## Workflow output", 1)[1]
        criteria = prompt.split("## Criteria", 1)[1].split("## Workflow output", 1)[0]
        count = sum(1 for line in criteria.splitlines() if line[:1].isdigit())
        score = 1 if "Canberra" in output else 0
        content = self.reply or (
            '{"criteria": ['
            + ", ".join(f'{{"criterion": {i + 1}, "score": {score}}}' for i in range(count))
            + '], "reasoning": "ok"}'
        )
        return LLMResponse(
            content=content,
            tool_calls=None,
            finish_reason="stop",
            usage=TokenUsage(input_tokens=100, output_tokens=20, cost_usd=0.002),
            model=self.model,
        )


def _workflow(text: str, action: str = "answer", extra_task: str = "") -> str:
    return f"""name: "Answer Question"
version: 1
first_task: think
tasks:
  think:
    name: Think
    action: {action}
    auto: true
    properties:
      text: "{text}"
{extra_task}
routings: []
"""


GOOD = _workflow("Canberra, a compromise between Sydney and Melbourne")
DEGRADED = _workflow("Sydney")

GOLDEN = """id: {id}
workflow: "Answer Question"
goal: "What is the capital of Australia?"
expected: "Canberra"
criteria:
  - "Names Canberra"
  - "Explains why it is not Sydney"
"""


@pytest.fixture
def judge(monkeypatch) -> _FakeJudge:
    fake = _FakeJudge()
    monkeypatch.setattr(gym_module, "get_llm", lambda *a, **k: fake)
    return fake


@pytest.fixture
def library(tmp_path: Path) -> WorkflowLibrary:
    golden = tmp_path / "golden"
    golden.mkdir()
    for golden_id in ("capital_1", "capital_2"):
        (golden / f"{golden_id}.yaml").write_text(GOLDEN.format(id=golden_id))
    lib = WorkflowLibrary(tmp_path / "library", golden_path=golden)
    lib.ensure_initialized()
    (lib.library_path / "answer_question.yaml").write_text(GOOD)
    return lib


@pytest.fixture
def metrics() -> InMemoryMetricsStore:
    return InMemoryMetricsStore()


@pytest.fixture
def engine(library, metrics) -> WorkflowEngine:
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("run_golden_gym", RunGoldenGymAction)
    registry.register_action("answer", _AnswerAction)
    registry.register_action("broken", _BrokenAction)
    registry.register_action("send_email", _EmailAction)
    registry.register_action("slow", _SlowAction)
    return WorkflowEngine(
        InMemoryStore(),
        registry,
        extras={"__workflow_library__": library, "__metrics_store__": metrics},
    )


GATE_YAML = """name: Gate
first_task: gym
tasks:
  gym:
    name: Gym
    action: run_golden_gym
    properties:
      candidates: "{{optimization_results.pending_gym}}"
routings: []
"""

ON_DEMAND_YAML = """name: Gym On Demand
first_task: gym
tasks:
  gym:
    name: Gym
    action: run_golden_gym
    properties:
      promote: false
routings: []
"""


def _candidate(modified: str, name: str = "Answer Question") -> dict:
    return {
        "name": name,
        "original_yaml": GOOD,
        "modified_yaml": modified,
        "llm_defined": False,
        "reason": "make it better",
        "change": {"type": "modify", "workflow": name, "action": "edit prompt"},
    }


async def _gate(engine, library, *candidates, continuation=None):
    definition = load_definition_from_yaml(GATE_YAML)
    results = {
        "changes_made": [],
        "modified_workflows": [],
        "failed_changes": [],
        "continuation_changes": continuation or [],
        "pending_gym": list(candidates),
    }
    process = await engine.create_process(
        definition,
        properties={
            "optimization_results": results,
            "__workflow_library_path__": str(library.library_path),
        },
    )
    await engine.start_process(process.id)
    return await engine.store.load_process(process.id)


def _saved_files(library) -> list[str]:
    return sorted(p.name for p in library.library_path.glob("*.yaml"))


async def test_degraded_candidate_is_rejected_and_not_saved(engine, library, metrics, judge):
    """O1: a modification that scores worse than the current version is blocked."""
    process = await _gate(engine, library, _candidate(DEGRADED))

    assert process.state == ProcessState.COMPLETE
    (decision,) = process.properties["golden_gym"]["decisions"]
    assert decision["decision"] == "rejected"
    assert decision["current_mean"] == 1.0
    assert decision["candidate_mean"] == 0.0
    assert "gym regression" in decision["reason"]

    results = process.properties["optimization_results"]
    assert results["changes_made"] == []
    assert results["modified_workflows"] == []
    (failed,) = results["failed_changes"]
    assert failed["workflow"] == "Answer Question"
    assert "candidate scored 0.00 vs current 1.00" in failed["reason"]
    assert results["pending_gym"] == []
    assert _saved_files(library) == ["answer_question.yaml"]

    scores = await metrics.get_gym_scores()
    assert len(scores) == 4  # 2 golden tasks x (current + candidate)
    assert {(s.variant, s.score) for s in scores} == {("current", 1.0), ("candidate", 0.0)}
    assert all(s.details["decision"] == "rejected" for s in scores)
    assert all(s.gym_run_id == process.id for s in scores)


async def test_equal_candidate_is_promoted_and_saved(engine, library, metrics, judge):
    """O2: a modification that scores no worse is saved as before."""
    better = _workflow("Canberra: chosen as a compromise")
    process = await _gate(engine, library, _candidate(better))

    (decision,) = process.properties["golden_gym"]["decisions"]
    assert decision["decision"] == "promoted"
    results = process.properties["optimization_results"]
    assert results["changes_made"] == [
        {"type": "modify", "workflow": "Answer Question", "action": "edit prompt"}
    ]
    assert results["modified_workflows"][0]["modified_yaml"] == better
    assert results["failed_changes"] == []
    assert _saved_files(library) == ["answer_question.yaml", "answer_question_1.yaml"]
    assert "compromise" in (library.library_path / "answer_question_1.yaml").read_text()


async def test_candidate_is_scored_separately_from_current(engine, library, judge):
    """Same name + version must not make both runs use one definition."""
    process = await _gate(engine, library, _candidate(DEGRADED))
    scores = process.properties["golden_gym"]["scores"]
    by_variant = {s["variant"]: s["score"] for s in scores}
    assert by_variant == {"current": 1.0, "candidate": 0.0}


async def test_within_tolerance_is_promoted(engine, library, judge):
    judge.reply = '{"criteria": [{"criterion": 1, "score": 1}, {"criterion": 2, "score": 1}]}'
    process = await _gate(engine, library, _candidate(DEGRADED))
    (decision,) = process.properties["golden_gym"]["decisions"]
    assert decision["decision"] == "promoted"


async def test_ungated_candidate_is_promoted_without_runs(engine, library, metrics, judge):
    """O2: a workflow with no golden tasks is saved as before, marked ungated."""
    candidate = _candidate(_workflow("anything").replace("Answer Question", "Brainstorm"))
    candidate["name"] = "Brainstorm"
    process = await _gate(engine, library, candidate)

    (decision,) = process.properties["golden_gym"]["decisions"]
    assert decision["decision"] == "promoted"
    assert decision["reason"] == "ungated: no golden tasks"
    assert judge.calls == 0
    assert await metrics.get_gym_scores() == []
    assert "brainstorm.yaml" in _saved_files(library)
    assert len(process.properties["optimization_results"]["changes_made"]) == 1


async def test_no_candidates_runs_nothing(engine, library, metrics, judge):
    process = await _gate(engine, library)
    assert process.state == ProcessState.COMPLETE
    assert process.properties["golden_gym"]["decisions"] == []
    assert judge.calls == 0


@pytest.mark.parametrize(
    ("modified", "reason"),
    [
        (
            _workflow(
                "Canberra",
                extra_task="  review:\n    name: Review\n    auto: false\n",
            ),
            "needs a human",
        ),
        (_workflow("Canberra", action="send_email"), "irreversible"),
        (_workflow("Canberra", action="no_such_action"), "not registered"),
        ("name: [broken", "could not load"),
    ],
)
async def test_unsafe_candidate_is_rejected_without_running(
    engine, library, judge, modified, reason
):
    """O5: the gym never runs what it cannot run safely; it rejects instead."""
    process = await _gate(engine, library, _candidate(modified))
    (decision,) = process.properties["golden_gym"]["decisions"]
    assert decision["decision"] == "rejected"
    assert reason in decision["reason"]
    assert judge.calls == 0
    assert _saved_files(library) == ["answer_question.yaml"]


async def test_unparseable_judge_reply_rejects(engine, library, judge):
    """O5: a run the judge cannot score fails the gate closed."""
    judge.reply = "I think it is fine"
    process = await _gate(engine, library, _candidate(_workflow("Canberra")))
    (decision,) = process.properties["golden_gym"]["decisions"]
    assert decision["decision"] == "rejected"
    assert "could not score" in decision["reason"]
    assert _saved_files(library) == ["answer_question.yaml"]


async def test_no_judge_provider_rejects_gated_but_saves_ungated(engine, library, monkeypatch):
    """O5: without an LLM judge gated candidates are rejected, ungated ones still saved."""

    def no_provider(*args, **kwargs):
        raise RuntimeError("no API key")

    monkeypatch.setattr(gym_module, "get_llm", no_provider)
    ungated = _candidate(_workflow("x").replace("Answer Question", "Brainstorm"))
    ungated["name"] = "Brainstorm"
    process = await _gate(engine, library, _candidate(_workflow("Canberra")), ungated)

    assert process.state == ProcessState.COMPLETE
    decisions = {d["workflow"]: d for d in process.properties["golden_gym"]["decisions"]}
    assert decisions["Answer Question"]["decision"] == "rejected"
    assert "no LLM judge" in decisions["Answer Question"]["reason"]
    assert decisions["Brainstorm"]["decision"] == "promoted"
    assert _saved_files(library) == ["answer_question.yaml", "brainstorm.yaml"]


async def test_failed_candidate_run_scores_zero_and_is_rejected(engine, library, judge):
    """O5: a candidate whose runs crash scores 0, so it cannot replace a working one."""
    process = await _gate(engine, library, _candidate(_workflow("x", action="broken")))
    (decision,) = process.properties["golden_gym"]["decisions"]
    assert decision["decision"] == "rejected"
    assert decision["candidate_mean"] == 0.0
    errors = [s["error"] for s in process.properties["golden_gym"]["scores"] if s["error"]]
    assert errors and all("workflow broke" in e for e in errors)


async def test_timed_out_candidate_run_is_rejected(engine, library, judge):
    """O5/O6: a candidate run that exceeds the per-run timeout fails and scores 0."""
    definition = load_definition_from_yaml(
        GATE_YAML.replace("properties:", "properties:\n      timeout: 0.2")
    )
    process = await engine.create_process(
        definition,
        properties={
            "optimization_results": {"pending_gym": [_candidate(_workflow("x", action="slow"))]},
            "__workflow_library_path__": str(library.library_path),
        },
    )
    await engine.start_process(process.id)
    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    (decision,) = process.properties["golden_gym"]["decisions"]
    assert decision["decision"] == "rejected"
    assert decision["candidate_mean"] == 0.0


async def test_run_cap_rejects_candidate(engine, library, judge):
    """O6: candidates that would exceed the run cap are rejected, not run."""
    definition = load_definition_from_yaml(
        GATE_YAML.replace("properties:", "properties:\n      max_runs: 3")
    )
    process = await engine.create_process(
        definition,
        properties={
            "optimization_results": {"pending_gym": [_candidate(_workflow("Canberra"))]},
            "__workflow_library_path__": str(library.library_path),
        },
    )
    await engine.start_process(process.id)
    process = await engine.store.load_process(process.id)
    (decision,) = process.properties["golden_gym"]["decisions"]
    assert decision["decision"] == "rejected"
    assert "run cap (3)" in decision["reason"]
    assert judge.calls == 0


async def test_continuation_status_follows_gate(engine, library, judge):
    pending = {"workflow": "Answer Question", "status": "pending_gym", "reason": ""}
    process = await _gate(engine, library, _candidate(DEGRADED), continuation=[pending])
    (change,) = process.properties["optimization_results"]["continuation_changes"]
    assert change["status"] == "failed"
    assert "gym regression" in change["reason"]


async def test_gym_cost_includes_runs_and_judge(engine, library, judge):
    process = await _gate(engine, library, _candidate(_workflow("Canberra")))
    # 4 runs at $0.01 each, plus 4 judge calls at the $0.002 OpenRouter reported
    assert process.properties["__total_cost__"] == pytest.approx(0.04 + 4 * 0.002)
    assert judge.calls == 4


async def test_on_demand_scores_current_workflows(engine, library, metrics, judge):
    """O3: with no candidates the gym scores the current version of each golden workflow."""
    definition = load_definition_from_yaml(ON_DEMAND_YAML)
    process = await engine.create_process(definition)
    await engine.start_process(process.id)
    process = await engine.store.load_process(process.id)

    report = process.properties["golden_gym"]
    assert report["mode"] == "on_demand"
    assert sorted(s["golden_id"] for s in report["scores"]) == ["capital_1", "capital_2"]
    assert all(s["score"] == 1.0 and s["variant"] == "current" for s in report["scores"])
    scores = await metrics.get_gym_scores(golden_id="capital_1")
    assert len(scores) == 1 and scores[0].workflow_name == "Answer Question"
    assert "decision" not in scores[0].details


async def test_check_only_candidates_from_run_inputs(engine, library, judge):
    """O1 on prod: Golden Gym checks a candidate passed as input and never saves it."""
    definition = load_definition_from_yaml(ON_DEMAND_YAML)
    process = await engine.create_process(
        definition,
        properties={"candidates": [{"name": "Answer Question", "modified_yaml": DEGRADED}]},
    )
    await engine.start_process(process.id)
    process = await engine.store.load_process(process.id)

    report = process.properties["golden_gym"]
    assert report["mode"] == "gate"
    assert report["promote"] is False
    (decision,) = report["decisions"]
    assert decision["decision"] == "rejected"
    assert _saved_files(library) == ["answer_question.yaml"]


async def test_golden_gym_workflow_file_runs(engine, library, judge):
    """The shipped Golden Gym workflow loads and scores on demand."""
    path = Path(__file__).parents[2] / "zebra-agent" / "workflows" / "golden_gym.yaml"
    definition = load_definition_from_yaml(path.read_text())
    process = await engine.create_process(definition)
    await engine.start_process(process.id)
    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    assert len(process.properties["golden_gym"]["scores"]) == 2


def test_unsafe_reason_accepts_pure_workflows(engine):
    definition = load_definition_from_yaml(GOOD)
    assert unsafe_reason(definition, engine.actions) is None


class TestOptimizerStaging:
    """workflow_optimizer with gym_gate stages modifications instead of saving them."""

    async def test_gym_gate_stages_modify(self, tmp_path, monkeypatch):
        optimizer = WorkflowOptimizerAction()
        results = {"modified_workflows": [], "changes_made": [], "pending_gym": []}
        results["continuation_changes"] = []

        async def fake_modify(*args, **kwargs):
            return DEGRADED, None

        monkeypatch.setattr(optimizer, "_modify_workflow", fake_modify)
        made = await optimizer._apply_priority(
            results,
            {"type": "fix", "target": "Answer Question", "action": "edit"},
            None,
            {},
            {"Answer Question": GOOD},
            "",
            None,
            dry_run=False,
            library_path=str(tmp_path),
            gym_gate=True,
        )
        assert made is True
        assert results["changes_made"] == []
        assert results["modified_workflows"] == []
        (staged,) = results["pending_gym"]
        assert staged["name"] == "Answer Question"
        assert staged["original_yaml"] == GOOD
        assert staged["modified_yaml"] == DEGRADED
        assert staged["change"] == {
            "type": "modify",
            "workflow": "Answer Question",
            "action": "edit",
        }
        assert list(tmp_path.iterdir()) == []

    async def test_without_gym_gate_saves_as_before(self, tmp_path, monkeypatch):
        optimizer = WorkflowOptimizerAction()
        results = {
            "modified_workflows": [],
            "changes_made": [],
            "pending_gym": [],
            "continuation_changes": [],
        }

        async def fake_modify(*args, **kwargs):
            return DEGRADED, None

        monkeypatch.setattr(optimizer, "_modify_workflow", fake_modify)
        await optimizer._apply_priority(
            results,
            {"type": "fix", "target": "Answer Question"},
            None,
            {},
            {"Answer Question": GOOD},
            "",
            None,
            dry_run=False,
            library_path=str(tmp_path),
        )
        assert results["pending_gym"] == []
        assert len(results["changes_made"]) == 1
        assert [p.name for p in tmp_path.iterdir()] == ["answer_question.yaml"]
