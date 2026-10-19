"""Outcome Review workflow, run directly (#190).

Runs the real built-in workflows (``outcome_review``, ``read_zebra_source``,
``search_zebra_source``) through ``run_named_workflow`` with a scripted model and
the real ``zebra_source`` action reading this checkout.
"""

import json
from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import TaskResult
from zebra.definitions.loader import load_definition, validate_definition
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.agent.outcome_review import CompareOutcomeReviewsAction
from zebra_tasks.agent.zebra_source import ZebraSourceAction
from zebra_tasks.llm.action import LLMCallAction
from zebra_tasks.llm.agent import LLMAgentAction
from zebra_tasks.llm.base import LLMProvider, LLMResponse, TokenUsage, ToolCall
from zebra_tasks.llm.client import set_llm_factory

from zebra_agent.direct_run import DirectRunError, run_named_workflow, workflow_status
from zebra_agent.library import WorkflowLibrary, list_goal_workflows

WORKFLOWS = Path(__file__).parent.parent / "workflows"
CLAUDE_SECRET = "claude-evidence-zebra-must-not-see-first"


def _verdicts(*pairs: tuple[str, str], evidence: str = "outcome_review.py:1") -> str:
    return json.dumps(
        {"verdicts": [{"id": i, "verdict": v, "evidence": evidence} for i, v in pairs]}
    )


def _response(content: str = "", tool_calls: list[ToolCall] | None = None) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason="tool_use" if tool_calls else "end_turn",
        usage=TokenUsage(300, 100),
        model="claude-sonnet-5-5",
    )


class ReviewModel(LLMProvider):
    """Reads one source file, then answers; reconsiders when asked to."""

    def __init__(self, review: str, reconsidered: str = ""):
        self.review = review
        self.reconsidered = reconsidered
        self.review_prompts: list[str] = []
        self.reconsider_prompts: list[str] = []
        self.tool_results: list[str] = []

    async def complete(self, messages, tools=None, temperature=0.7, max_tokens=4096, **kw):
        text = "\n".join(str(m.content) for m in messages)
        reconsidering = "disagreed with you" in text
        (self.reconsider_prompts if reconsidering else self.review_prompts).append(text)
        tool_results = [m.content for m in messages if m.role.value == "tool"]
        if not tool_results:
            return _response(
                tool_calls=[
                    ToolCall(
                        "r1",
                        "read_zebra_source",
                        {
                            "path": "zebra-tasks/zebra_tasks/agent/outcome_review.py",
                            "start_line": 1,
                            "end_line": 3,
                        },
                    )
                ]
            )
        self.tool_results.extend(tool_results)
        return _response(self.reconsidered if reconsidering else self.review)

    async def stream(self, *args, **kwargs):
        raise NotImplementedError
        yield ""

    @property
    def name(self) -> str:
        return "review-model"

    @property
    def model(self) -> str:
        return "claude-sonnet-5-5"

    @property
    def max_context_tokens(self) -> int:
        return 200_000


@pytest.fixture
def library(tmp_path: Path) -> WorkflowLibrary:
    lib = WorkflowLibrary(tmp_path / "workflows")
    lib.copy_builtin_workflows(WORKFLOWS)
    return lib


@pytest.fixture
def engine(library, monkeypatch) -> WorkflowEngine:
    monkeypatch.delenv("ZEBRA_SOURCE_ROOT", raising=False)
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("llm_agent", LLMAgentAction)
    registry.register_action("llm_call", LLMCallAction)
    registry.register_action("zebra_source", ZebraSourceAction)
    registry.register_action("compare_outcome_reviews", CompareOutcomeReviewsAction)
    return WorkflowEngine(InMemoryStore(), registry, extras={"__workflow_library__": library})


def _inputs() -> dict:
    return {
        "issue": "190",
        "title": "Outcome review",
        "outcomes": "| O1 | Reviews compare | test |\n| O2 | Disputes escalate | test |",
        "diff": "+ class CompareOutcomeReviewsAction",
        "deployed_hash": "abc1234",
        "claude_review": {
            "verdicts": [
                {"id": "O1", "verdict": "met", "evidence": CLAUDE_SECRET},
                {"id": "O2", "verdict": "partial", "evidence": CLAUDE_SECRET},
            ]
        },
    }


async def _run(engine, library, model: ReviewModel) -> dict:
    set_llm_factory(lambda m: model)
    return await run_named_workflow(engine, library, "Outcome Review", _inputs(), model="medium")


@pytest.mark.parametrize(
    "filename", ["outcome_review.yaml", "read_zebra_source.yaml", "search_zebra_source.yaml"]
)
def test_workflow_is_valid(filename):
    assert validate_definition(load_definition(WORKFLOWS / filename)) == []


async def test_review_workflows_are_never_selected_for_goals(library):
    names = {w["name"] for w in await list_goal_workflows(library)}

    assert not names & {"Outcome Review", "Read Zebra Source", "Search Zebra Source"}


async def test_agreement_completes_without_a_human(engine, library):
    model = ReviewModel(_verdicts(("O1", "met"), ("O2", "partial")))

    status = await _run(engine, library, model)

    assert status["status"] == "complete"
    assert status["task_id"] is None
    assert status["output"]["status"] == "agreed"
    assert status["output"]["followups"] == ["O2"]
    assert "| O1 | met | met | yes |" in status["output"]["table_markdown"]
    # Zebra read its own source through the tool, and never saw Claude's verdicts first.
    assert model.tool_results[0].startswith('    1| """CompareOutcomeReviewsAction')
    assert all(CLAUDE_SECRET not in p for p in model.review_prompts)
    assert model.reconsider_prompts == []


async def test_zebra_reconsidering_can_settle_a_dispute(engine, library):
    model = ReviewModel(
        _verdicts(("O1", "met"), ("O2", "met")),
        reconsidered=_verdicts(("O2", "partial")),
    )

    status = await _run(engine, library, model)

    assert status["status"] == "complete"
    assert status["output"]["status"] == "agreed"
    assert any(CLAUDE_SECRET in p for p in model.reconsider_prompts)


async def test_a_lasting_dispute_waits_for_a_human_ruling(engine, library):
    model = ReviewModel(
        _verdicts(("O1", "met"), ("O2", "met")),
        reconsidered=_verdicts(("O2", "met"), evidence="tests cover it"),
    )

    status = await _run(engine, library, model)

    assert status["status"] == "awaiting_input"
    assert status["task_name"] == "Outcome Review — Your Ruling"

    await engine.complete_task(status["task_id"], TaskResult.ok(output={"ruling": "O2 partial"}))
    status = await workflow_status(engine, status["process_id"])

    assert status["status"] == "complete"
    assert status["output"]["status"] == "ruled"
    assert status["output"]["ruling"] == "O2 partial"
    assert status["output"]["disputed"] == ["O2"]


async def test_missing_inputs_or_unknown_workflow_do_not_start(engine, library):
    with pytest.raises(DirectRunError, match="claude_review"):
        await run_named_workflow(engine, library, "Outcome Review", {"outcomes": "x", "diff": "y"})
    with pytest.raises(DirectRunError, match="No workflow"):
        await run_named_workflow(engine, library, "No Such Workflow", {})


async def test_status_of_unknown_process_is_failed(engine):
    status = await workflow_status(engine, "nope")

    assert status["status"] == "failed"
