"""Outcome Review workflow, run directly (#190, #211).

Runs the real built-in workflows (``outcome_review``, ``list_zebra_source``,
``read_zebra_source``, ``search_zebra_source``) through ``run_named_workflow`` with a
scripted model and the real ``zebra_source`` action reading this checkout.
"""

import json
from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import TaskResult
from zebra.definitions.loader import load_definition, validate_definition
from zebra.forms import resolve_task_schema
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.agent.outcome_review import (
    BriefOutcomeDisputesAction,
    CompareOutcomeReviewsAction,
)
from zebra_tasks.agent.zebra_source import ZebraSourceAction
from zebra_tasks.llm.action import LLMCallAction
from zebra_tasks.llm.agent import LLMAgentAction
from zebra_tasks.llm.base import LLMProvider, LLMResponse, TokenUsage, ToolCall
from zebra_tasks.llm.client import set_llm_factory

from zebra_agent.direct_run import DirectRunError, run_named_workflow, workflow_status
from zebra_agent.library import WorkflowLibrary, list_goal_workflows

WORKFLOWS = Path(__file__).parent.parent / "workflows"
AGENT_DIR = "zebra-tasks/zebra_tasks/agent"
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
        model="test/model",
    )


class ReviewModel(LLMProvider):
    """Reads one source file, then answers; reconsiders when asked to.

    ``reconsidered`` may be a list of replies, one per reconsidering answer. ``brief`` answers
    the dispute brief (#295); ``None`` makes that call raise.
    """

    def __init__(
        self,
        review: str,
        reconsidered: str | list[str] = "",
        calls: list[ToolCall] | None = None,
        brief: str | None = None,
    ):
        self.review = review
        self.reconsidered = reconsidered
        self.calls = calls
        self.brief = brief
        self.review_prompts: list[str] = []
        self.reconsider_prompts: list[str] = []
        self.brief_prompts: list[str] = []
        self.tool_results: list[str] = []

    async def complete(self, messages, tools=None, temperature=0.7, max_tokens=4096, **kw):
        text = "\n".join(str(m.content) for m in messages)
        if "make the disagreement easy to see" in text:
            self.brief_prompts.append(text)
            if self.brief is None:
                raise RuntimeError("brief model down")
            return _response(self.brief)
        reconsidering = "disagreed with you" in text
        (self.reconsider_prompts if reconsidering else self.review_prompts).append(text)
        tool_results = [m.content for m in messages if m.role.value == "tool"]
        if not tool_results:
            return _response(
                tool_calls=self.calls
                or [
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
        if not reconsidering:
            return _response(self.review)
        if isinstance(self.reconsidered, list):
            return _response(self.reconsidered.pop(0))
        return _response(self.reconsidered)

    async def stream(self, *args, **kwargs):
        raise NotImplementedError
        yield ""

    @property
    def name(self) -> str:
        return "review-model"

    @property
    def model(self) -> str:
        return "test/model"

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
    registry.register_action("brief_outcome_disputes", BriefOutcomeDisputesAction)
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


async def _run(engine, library, model: ReviewModel, **inputs) -> dict:
    set_llm_factory(lambda m: model)
    return await run_named_workflow(
        engine, library, "Outcome Review", {**_inputs(), **inputs}, model="medium"
    )


@pytest.mark.parametrize(
    "filename",
    [
        "outcome_review.yaml",
        "list_zebra_source.yaml",
        "read_zebra_source.yaml",
        "search_zebra_source.yaml",
    ],
)
def test_workflow_is_valid(filename):
    assert validate_definition(load_definition(WORKFLOWS / filename)) == []


async def test_review_workflows_are_never_selected_for_goals(library):
    names = {w["name"] for w in await list_goal_workflows(library)}

    assert not names & {
        "Outcome Review",
        "List Zebra Source",
        "Read Zebra Source",
        "Search Zebra Source",
    }


async def test_review_can_list_source_and_recover_from_a_bad_path(engine, library):
    model = ReviewModel(
        _verdicts(("O1", "met"), ("O2", "partial")),
        calls=[
            ToolCall("l1", "list_zebra_source", {"path": AGENT_DIR}),
            ToolCall("r1", "read_zebra_source", {"path": f"{AGENT_DIR}/outcome_reviw.py"}),
            ToolCall("r2", "read_zebra_source", {"path": f"{AGENT_DIR}/outcome.py"}),
        ],
    )

    status = await _run(engine, library, model)

    assert status["status"] == "complete"
    listing, typo_read, bad_read = model.tool_results
    assert "zebra-tasks/zebra_tasks/agent/outcome_review.py (" in listing
    # One clear match is read in the same call (#223)
    assert "read 'zebra-tasks/zebra_tasks/agent/outcome_review.py' instead" in typo_read
    assert "def parse_review" in typo_read
    assert "zebra-tasks/zebra_tasks/agent/outcome_review.py" in bad_read.split("Did you mean: ")[1]
    assert "list_zebra_source" in bad_read


async def test_read_tool_returns_exactly_the_requested_range(engine, library):
    """Read Zebra Source passes start_line / end_line through (#285: dream v10 did not)."""
    model = ReviewModel(
        _verdicts(("O1", "met"), ("O2", "partial")),
        calls=[
            ToolCall(
                "r1",
                "read_zebra_source",
                {"path": f"{AGENT_DIR}/outcome_review.py", "start_line": 20, "end_line": 25},
            )
        ],
    )

    status = await _run(engine, library, model)

    assert status["status"] == "complete"
    (read,) = model.tool_results
    numbers = [int(line.split("|", 1)[0]) for line in read.splitlines() if "|" in line]
    assert numbers == list(range(20, 26))


async def test_list_tool_takes_brace_globs_and_a_glob_as_path(engine, library):
    model = ReviewModel(
        _verdicts(("O1", "met"), ("O2", "partial")),
        calls=[
            ToolCall("l1", "list_zebra_source", {"path": f"{AGENT_DIR}/outcome_*.py"}),
            ToolCall(
                "l2",
                "list_zebra_source",
                {"path": ".", "glob": f"{AGENT_DIR}/{{outcome_review,zebra_source}}.py"},
            ),
        ],
    )

    status = await _run(engine, library, model)

    assert status["status"] == "complete"
    as_path, braces = model.tool_results
    assert f"{AGENT_DIR}/outcome_review.py" in as_path
    assert braces.splitlines() == [f"{AGENT_DIR}/outcome_review.py", f"{AGENT_DIR}/zebra_source.py"]


async def test_review_prompt_shows_the_change_map_before_the_diff(engine, library):
    model = ReviewModel(_verdicts(("O1", "met"), ("O2", "partial")))
    change_map = "Files changed (1):\n- a.py (+1 -0)"

    await _run(engine, library, model, change_map=change_map)

    prompt = model.review_prompts[0]
    assert f"## Change map\n{change_map}" in prompt
    assert prompt.index("## Change map") < prompt.index("## Diff")


@pytest.mark.parametrize(
    ("filename", "prod_copy"),
    [
        ("read_zebra_source.yaml", 10),
        ("list_zebra_source.yaml", 3),
        ("search_zebra_source.yaml", 2),
    ],
)
def test_source_tools_ship_above_the_prod_dream_copies(filename, prod_copy):
    """Only a higher version replaces the broken dream copies on prod (#224, #285)."""
    assert load_definition(WORKFLOWS / filename).version > prod_copy


def test_review_tool_budget_is_tight():
    tasks = load_definition(WORKFLOWS / "outcome_review.yaml").tasks

    assert tasks["zebra_review"].properties["max_tool_turns"] == 8
    assert tasks["zebra_reconsider"].properties["max_tool_turns"] == 5
    assert tasks["zebra_review"].properties["answer_on_budget"] is True
    assert tasks["zebra_reconsider"].properties["answer_on_budget"] is True


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


async def test_junk_reconsideration_is_asked_for_again(engine, library):
    model = ReviewModel(
        _verdicts(("O1", "met"), ("O2", "met")),
        reconsidered=[" the", _verdicts(("O2", "partial"))],
    )

    status = await _run(engine, library, model)

    assert status["status"] == "complete"
    assert status["output"]["status"] == "agreed"
    assert model.reconsidered == []
    assert "could not be parsed as JSON" in model.reconsider_prompts[-1]


async def test_reconsideration_that_stays_junk_fails_the_review(engine, library):
    model = ReviewModel(_verdicts(("O1", "met"), ("O2", "met")), reconsidered=" the")

    status = await _run(engine, library, model)

    # Zebra never reconsidered, so there is nothing to put to a human (#216).
    assert status["status"] == "failed"
    assert status["task_id"] is None
    process = await engine.store.load_process(status["process_id"])
    assert "Unusable JSON answer" in process.properties["__error__"]
    assert "zebra_reconsidered" not in process.properties


BRIEF = json.dumps(
    {
        "disputes": [
            {
                "id": "O2",
                "crux": "Whether a lasting dispute is covered by a test",
                "zebra": "Tests cover it.",
                "claude": "Only the happy path is tested.",
                "settle": "Read test_outcome_review_workflow.py.",
            }
        ]
    }
)


async def test_a_lasting_dispute_waits_for_a_human_ruling(engine, library):
    model = ReviewModel(
        _verdicts(("O1", "met"), ("O2", "met")),
        reconsidered=_verdicts(("O2", "met"), evidence="tests cover it"),
        brief=BRIEF,
    )

    status = await _run(engine, library, model)

    assert status["status"] == "awaiting_input"
    assert status["task_name"] == "Outcome Review — Your Ruling"

    # One brief call sees both sides' cases; the agreed outcome is not in it (#295)
    (brief_prompt,) = model.brief_prompts
    assert "tests cover it" in brief_prompt and CLAUDE_SECRET in brief_prompt
    assert "## O1" not in brief_prompt

    # The form is generated: the crux and a required pick per disputed outcome (#295)
    process = await engine.store.load_process(status["process_id"])
    form = (await engine.store.load_definition(process.definition_id)).tasks["human_ruling"]
    assert form.properties["show_prior_outputs"] is False
    schema = resolve_task_schema(form.properties["schema"], process.properties)
    fields = schema["properties"]
    assert schema["title"] == "Zebra and Claude disagree on 1 of 2 outcomes"
    assert schema["description"].startswith("#190 Outcome review (abc1234)")
    assert schema["required"] == ["O2"]
    assert fields["agreed"]["default"] == "O1 met"
    case = fields["O2_case"]["default"]
    assert "*Disputes escalate*" in case
    assert "**In dispute:** Whether a lasting dispute is covered by a test" in case
    assert "| **Zebra** | met | Tests cover it. |" in case
    assert "| **Claude** | partial | Only the happy path is tested. |" in case
    assert "**What would settle it:** Read test_outcome_review_workflow.py." in case
    assert fields["O2"]["enumLabels"] == ["Met (Zebra)", "Partial (Claude)", "Missed"]
    assert f"**Claude:** {CLAUDE_SECRET}" in fields["evidence"]["default"]

    await engine.complete_task(
        status["task_id"],
        TaskResult.ok(output={"O2": "partial", "O2_note": "add a dispute test"}),
    )
    status = await workflow_status(engine, status["process_id"])

    assert status["status"] == "complete"
    output = status["output"]
    assert output["status"] == "ruled"
    assert output["disputed"] == ["O2"]
    assert output["ruling"] == "O2: partial: add a dispute test"
    assert output["followups"] == ["O2"]
    assert output["unruled"] == []
    assert (
        "| O2 | met | partial | **no** | **partial** (add a dispute test) |"
        in (output["table_markdown"])
    )
    assert output["briefs"]["O2"]["crux"].startswith("Whether a lasting dispute")


async def test_a_failed_brief_still_asks_for_a_ruling(engine, library):
    """With the brief model down the form shows each side's first sentence (#295)."""
    model = ReviewModel(
        _verdicts(("O1", "met"), ("O2", "met")),
        reconsidered=_verdicts(("O2", "met"), evidence="Tests cover it. More detail."),
        brief=None,
    )

    status = await _run(engine, library, model)

    assert status["status"] == "awaiting_input"
    process = await engine.store.load_process(status["process_id"])
    result = process.properties["review_result"]
    assert result["briefs"] == {}
    case = result["ruling_form"]["properties"]["O2_case"]["default"]
    assert "In dispute" not in case
    assert "| **Zebra** | met | Tests cover it. |" in case


async def test_missing_inputs_or_unknown_workflow_do_not_start(engine, library):
    with pytest.raises(DirectRunError, match="claude_review"):
        await run_named_workflow(engine, library, "Outcome Review", {"outcomes": "x", "diff": "y"})
    with pytest.raises(DirectRunError, match="No workflow"):
        await run_named_workflow(engine, library, "No Such Workflow", {})


async def test_status_of_unknown_process_is_failed(engine):
    status = await workflow_status(engine, "nope")

    assert status["status"] == "failed"
