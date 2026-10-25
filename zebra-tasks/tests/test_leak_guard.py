"""Tests for the leak guard on LLM-written workflows (#237)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from zebra_tasks.agent.leak_guard import (
    GOAL,
    MAX_REPORTED_HITS,
    RUN,
    LeakGuard,
    apply_guard,
    generalise_prompt,
    run_texts_from_metrics,
)
from zebra_tasks.llm.base import LLMResponse, TokenUsage
from zebra_tasks.llm.client import set_llm_factory

RUN_TEXT = "Update the Acme Corp migration plan for Jane Smith (jane@acme.com), budget 4,500"


def _workflow(prompt: str, task_id: str = "step1", name: str = "Project Update") -> str:
    return f"""name: "{name}"
description: "Update a project plan"
first_task: {task_id}
tasks:
  {task_id}:
    name: "Step"
    action: llm_call
    auto: true
    properties:
      prompt: "{prompt}"
"""


CLEAN = _workflow("Update the project plan described in the goal: {{goal}}")
COPYING = _workflow("Check Acme Corp's SLA with Jane Smith: {{goal}}")


def _kinds(hits) -> set[tuple[str, str]]:
    return {(h.kind, h.text) for h in hits}


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


class TestDetectors:
    def test_names_from_runs(self):
        hits = LeakGuard(run_texts=[RUN_TEXT]).check(COPYING)
        assert {("name", "Acme"), ("name", "Corp"), ("name", "Jane"), ("name", "Smith")} <= (
            _kinds(hits)
        )
        assert all(h.source == RUN for h in hits)
        assert hits[0].where == "tasks.step1.properties.prompt"

    def test_snake_case_task_id(self):
        wf = _workflow("{{goal}}", task_id="check_acme").replace(
            "first_task: check_acme", "first_task: start"
        )
        hits = LeakGuard(run_texts=[RUN_TEXT]).check(wf)
        assert [(h.kind, h.text, h.where) for h in hits] == [("name", "Acme", "tasks.check_acme")]

    def test_acronyms_are_not_names(self):
        guard = LeakGuard(run_texts=["Ask Jane Smith at Acme Corp about the SLA and API"])
        assert guard.check(_workflow("Report SLA status and API health: {{goal}}")) == []

    def test_email_domain_and_number(self):
        wf = _workflow("Email jane@acme.com or see https://www.acme.com about 4500 {{goal}}")
        kinds = _kinds(LeakGuard(run_texts=[RUN_TEXT]).check(wf))
        assert ("email", "jane@acme.com") in kinds
        assert ("domain", "acme.com") in kinds
        assert ("number", "4500") in kinds

    def test_run_phrase_of_four_tokens(self):
        run = "the quarterly churn report keeps missing regional totals"
        wf = _workflow("Remember the quarterly churn report keeps failing. {{goal}}")
        assert ("phrase", "the quarterly churn report keeps") in _kinds(
            LeakGuard(run_texts=[run]).check(wf)
        )

    def test_stopword_only_phrase_is_not_a_hit(self):
        run = "it is one of the best"
        wf = _workflow("Pick it is one of the options {{goal}}")
        assert LeakGuard(run_texts=[run]).check(wf) == []

    def test_goal_topic_words_pass(self):
        guard = LeakGuard(goal_texts=["plan a birthday party for my friend next month"])
        wf = _workflow("Plan a birthday party: {{goal}}", name="Birthday Party Planner")
        assert guard.check(wf) == []

    def test_long_goal_copy_is_a_goal_hit(self):
        goal = "write a summary of the board meeting notes and send it to the team"
        wf = _workflow(f"Please {goal} today")
        hits = LeakGuard(goal_texts=[goal]).check(wf)
        assert [(h.kind, h.source) for h in hits] == [("phrase", GOAL)]

    def test_goal_name_is_a_goal_hit(self):
        hits = LeakGuard(goal_texts=["Write a cover letter for Globex"]).check(
            _workflow("Write a cover letter for Globex: {{goal}}")
        )
        assert [(h.kind, h.text, h.source) for h in hits] == [("name", "Globex", GOAL)]

    def test_specific_in_run_and_goal_is_a_run_hit(self):
        hits = LeakGuard(run_texts=["ask Globex"], goal_texts=["email Globex"]).check(
            _workflow("Ask Globex {{goal}}")
        )
        assert [(h.text, h.source) for h in hits] == [("Globex", RUN)]

    def test_sentence_initial_words_are_not_names(self):
        run = "Update the plan. Check totals.\n- Review numbers\n1. Send report"
        wf = _workflow("Update, check, review and send: {{goal}}")
        assert LeakGuard(run_texts=[run]).check(wf) == []

    def test_text_in_parent_is_allowed(self):
        assert LeakGuard(run_texts=[RUN_TEXT], parent_yaml=COPYING).check(COPYING) == []

    def test_kept_name_in_changed_literal_is_allowed(self):
        parent = _workflow("Ask Acme Corp about {{goal}}")
        child = _workflow("Ask Acme Corp politely about {{goal}}")
        assert LeakGuard(run_texts=[RUN_TEXT], parent_yaml=parent).check(child) == []

    def test_words_zebra_supplied_are_allowed(self):
        guard = LeakGuard(
            goal_texts=["Write a script in Python for the Kagi results"],
            allow_text="python_exec runs Python code. kagi_search searches with Kagi.",
        )
        assert guard.check(_workflow("You write Python using Kagi results. {{goal}}")) == []

    def test_templates_are_ignored(self):
        guard = LeakGuard(run_texts=["ask Jane about the plan"])
        assert guard.check(_workflow("{{Jane}} {{goal}}")) == []

    def test_hits_are_deduplicated_and_capped(self):
        names = " ".join(f"Name{chr(65 + i)}x" for i in range(20))
        guard = LeakGuard(run_texts=[f"call {names}"])
        wf = _workflow(f"call {names}") + '  step2:\n    name: "call NameAx"\n'
        hits = guard.check(wf)
        assert len(hits) == MAX_REPORTED_HITS
        assert len({(h.kind, h.text) for h in hits}) == len(hits)

    def test_generalise_prompt_lists_hits(self):
        hits = LeakGuard(run_texts=[RUN_TEXT]).check(COPYING)
        prompt = generalise_prompt(hits)
        assert '"Acme" (name, in tasks.step1.properties.prompt)' in prompt
        assert "{{goal}}" in prompt


def test_run_texts_from_metrics():
    metrics = {
        "failure_patterns": [
            {
                "workflow_name": "Billing",
                "error_types": {"Timeout calling Acme API": 2},
                "sample_goals": ["Fix Jane's invoice"],
            }
        ],
        "continuation_analysis": {
            "frequently_continued": [{"comments": ["also email Bob"]}],
            "capability_gaps": [{"comment": "", "rationale": "needed Globex data"}],
            "proposals": [{"action": "Extend 'Billing' so users no longer need to continue it."}],
        },
    }
    assert run_texts_from_metrics(metrics) == [
        "Timeout calling Acme API",
        "Fix Jane's invoice",
        "also email Bob",
        "needed Globex data",
    ]
    assert run_texts_from_metrics(None) == []


# ---------------------------------------------------------------------------
# apply_guard
# ---------------------------------------------------------------------------


class TestApplyGuard:
    async def test_clean_workflow_is_not_regenerated(self):
        regenerate = AsyncMock()
        result = await apply_guard(LeakGuard(run_texts=[RUN_TEXT]), CLEAN, regenerate, reject=True)
        assert result == (CLEAN, None, None)
        regenerate.assert_not_called()

    async def test_generalised_rewrite_is_used(self):
        regenerate = AsyncMock(return_value=(CLEAN, None))
        yaml_out, problem, record = await apply_guard(
            LeakGuard(run_texts=[RUN_TEXT]), COPYING, regenerate, reject=True
        )
        assert (yaml_out, problem) == (CLEAN, None)
        assert record["status"] == "generalised"
        assert {"kind": "name", "text": "Acme"}.items() <= record["hits"][0].items()
        regenerate.assert_awaited_once()
        assert "Acme" in regenerate.await_args.args[0]

    async def test_second_hit_rejects_when_reject(self):
        regenerate = AsyncMock(return_value=(COPYING, None))
        yaml_out, problem, record = await apply_guard(
            LeakGuard(run_texts=[RUN_TEXT]), COPYING, regenerate, reject=True
        )
        assert yaml_out is None
        assert problem.startswith("Leak guard:") and '"Acme" (name)' in problem
        assert record["status"] == "rejected"
        regenerate.assert_awaited_once()

    async def test_second_hit_is_kept_when_not_reject(self):
        regenerate = AsyncMock(return_value=(COPYING, None))
        yaml_out, problem, record = await apply_guard(
            LeakGuard(run_texts=[RUN_TEXT]), COPYING, regenerate, reject=False
        )
        assert (yaml_out, problem) == (COPYING, None)
        assert record["status"] == "kept"

    async def test_unusable_rewrite_falls_back_to_the_first_hits(self):
        regenerate = AsyncMock(return_value=(None, "Invalid workflow YAML"))
        guard = LeakGuard(run_texts=[RUN_TEXT])
        assert (await apply_guard(guard, COPYING, regenerate, reject=True))[0] is None
        kept = await apply_guard(guard, COPYING, regenerate, reject=False)
        assert kept[0] == COPYING and kept[2]["status"] == "kept"

    async def test_guard_error_fails_closed_when_reject(self):
        guard = MagicMock()
        guard.check = MagicMock(side_effect=RuntimeError("boom"))
        yaml_out, problem, record = await apply_guard(guard, COPYING, AsyncMock(), reject=True)
        assert yaml_out is None and "check failed" in problem
        assert record["status"] == "rejected" and record["error"] == "boom"

    async def test_guard_error_keeps_and_records_when_not_reject(self):
        guard = MagicMock()
        guard.check = MagicMock(side_effect=RuntimeError("boom"))
        yaml_out, problem, record = await apply_guard(guard, COPYING, AsyncMock(), reject=False)
        assert (yaml_out, problem) == (COPYING, None)
        assert record["status"] == "error"


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def _response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=None,
        finish_reason="end_turn",
        usage=TokenUsage(input_tokens=10, output_tokens=20),
        model="test-model",
    )


@pytest.fixture
def context():
    ctx = MagicMock()
    ctx.process.id = "process-1"
    ctx.process.properties = {}
    ctx.extras = {}
    ctx.get_process_property = MagicMock(
        side_effect=lambda k, d=None: ctx.process.properties.get(k, d)
    )
    ctx.set_process_property = MagicMock(
        side_effect=lambda k, v: ctx.process.properties.__setitem__(k, v)
    )
    ctx.resolve_template = MagicMock(side_effect=lambda x: x)
    ctx.engine.actions.format_for_prompt = MagicMock(return_value="## Actions\n- llm_call\n")
    ctx.engine.actions.has_action = MagicMock(side_effect=lambda name: name == "llm_call")
    return ctx


def _provider(*contents: str) -> MagicMock:
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=[_response(c) for c in contents])
    set_llm_factory(lambda model: provider)
    return provider


ORIGINAL = _workflow("Update the plan: {{goal}}")
SAMPLE_GOALS = [
    "Update the Acme Corp migration plan for Jane Smith",
    "Ask Jane Smith at Acme Corp about the SLA",
]


def _evaluation(ptype: str = "fix") -> dict:
    return {
        "improvement_priorities": [
            {"type": ptype, "target": "Project Update", "action": "add an SLA check"}
        ],
        "new_workflow_suggestions": [],
        "workflow_evaluations": [],
        "run_exposure": SAMPLE_GOALS,
    }


def _optimizer_task(tmp_path, evaluation: dict, gym_gate: bool = False) -> MagicMock:
    task = MagicMock()
    task.properties = {
        "evaluation": evaluation,
        "existing_workflows": {"Project Update": ORIGINAL},
        "dry_run": False,
        "gym_gate": gym_gate,
        "workflow_library_path": str(tmp_path),
    }
    return task


ACME_JANE = _workflow("Check Acme Corp's SLA with Jane Smith: {{goal}}")
GENERALISED = _workflow("Check the SLA of the client and contact named in the goal: {{goal}}")


class TestOptimizer:
    async def test_acme_and_jane_are_generalised(self, context, tmp_path):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        provider = _provider(ACME_JANE, GENERALISED)
        result = await WorkflowOptimizerAction().run(
            _optimizer_task(tmp_path, _evaluation()), context
        )

        assert result.success
        (saved,) = tmp_path.iterdir()
        text = saved.read_text()
        assert "Acme" not in text and "Jane" not in text
        (change,) = result.output["changes_made"]
        assert change["leak_guard"]["status"] == "generalised"
        assert result.output["failed_changes"] == []
        # The rewrite saw its own YAML and the list of specifics
        retry_messages = provider.complete.await_args_list[1].kwargs["messages"]
        assert retry_messages[-2].content == ACME_JANE.strip()
        assert '"Acme"' in retry_messages[-1].content

    async def test_copying_twice_is_rejected_and_nothing_saved(self, context, tmp_path):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        provider = _provider(ACME_JANE, ACME_JANE)
        result = await WorkflowOptimizerAction().run(
            _optimizer_task(tmp_path, _evaluation()), context
        )

        assert result.success
        assert list(tmp_path.iterdir()) == []
        assert result.output["changes_made"] == []
        assert result.output["modified_workflows"] == []
        (failed,) = result.output["failed_changes"]
        assert failed["reason"].startswith("Leak guard")
        assert {h["text"] for h in failed["leak_hits"]} >= {"Acme", "Jane"}
        assert provider.complete.await_count == 2  # exactly one regeneration

    async def test_rejection_is_not_staged_for_the_gym(self, context, tmp_path):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        _provider(ACME_JANE, ACME_JANE)
        result = await WorkflowOptimizerAction().run(
            _optimizer_task(tmp_path, _evaluation(), gym_gate=True), context
        )
        assert result.output["pending_gym"] == []
        assert result.output["failed_changes"][0]["leak_hits"]

    async def test_generalised_change_is_staged_for_the_gym(self, context, tmp_path):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        _provider(ACME_JANE, GENERALISED)
        result = await WorkflowOptimizerAction().run(
            _optimizer_task(tmp_path, _evaluation(), gym_gate=True), context
        )
        (staged,) = result.output["pending_gym"]
        assert staged["modified_yaml"] == GENERALISED.strip()
        assert staged["change"]["leak_guard"]["status"] == "generalised"

    async def test_created_workflow_is_guarded(self, context, tmp_path):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        _provider(ACME_JANE, ACME_JANE)
        result = await WorkflowOptimizerAction().run(
            _optimizer_task(tmp_path, _evaluation("create")), context
        )
        assert list(tmp_path.iterdir()) == []
        assert result.output["failed_changes"][0]["type"] == "create"

    async def test_clean_change_uses_one_call(self, context, tmp_path):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        provider = _provider(GENERALISED)
        result = await WorkflowOptimizerAction().run(
            _optimizer_task(tmp_path, _evaluation()), context
        )
        assert provider.complete.await_count == 1
        assert "leak_guard" not in result.output["changes_made"][0]

    async def test_prompt_states_the_rule(self):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        assert "Never copy goals, names" in WorkflowOptimizerAction._PROMPT_FOOTER


class TestCreator:
    def _task(self, goal: str) -> MagicMock:
        task = MagicMock()
        task.properties = {"goal": goal, "output_key": "created_workflow"}
        return task

    async def test_goal_specifics_are_generalised(self, context):
        from zebra_tasks.agent.creator import WorkflowCreatorAction

        library = MagicMock()
        context.extras["__workflow_library__"] = library
        provider = _provider(
            _workflow("Write a cover letter for Globex Industries: {{goal}}", name="Cover Letter"),
            _workflow("Write a cover letter for the company in the goal: {{goal}}"),
        )
        result = await WorkflowCreatorAction().run(
            self._task("Write a cover letter for Globex Industries"), context
        )

        assert result.success
        assert provider.complete.await_count == 2
        saved = library.add_workflow.call_args.args[0]
        assert "Globex" not in saved
        assert result.output["leak_guard"]["status"] == "generalised"

    async def test_remaining_goal_specifics_are_kept_not_failed(self, context):
        from zebra_tasks.agent.creator import WorkflowCreatorAction

        library = MagicMock()
        context.extras["__workflow_library__"] = library
        copy = _workflow("Write a cover letter for Globex Industries: {{goal}}")
        _provider(copy, copy)
        result = await WorkflowCreatorAction().run(
            self._task("Write a cover letter for Globex Industries"), context
        )

        assert result.success
        library.add_workflow.assert_called_once()
        assert result.output["leak_guard"]["status"] == "kept"

    async def test_topic_words_need_one_call(self, context):
        from zebra_tasks.agent.creator import WorkflowCreatorAction

        context.extras["__workflow_library__"] = MagicMock()
        provider = _provider(
            _workflow("Plan a birthday party: {{goal}}", name="Birthday Party Planner")
        )
        result = await WorkflowCreatorAction().run(
            self._task("Plan a birthday party for my friend"), context
        )
        assert result.success
        assert provider.complete.await_count == 1
        assert "leak_guard" not in result.output

    async def test_previous_run_content_is_exposure(self, context):
        from zebra_tasks.agent.creator import WorkflowCreatorAction

        context.extras["__workflow_library__"] = MagicMock()
        context.process.properties.update(
            {
                "previous_run_context": {"goal": "Draft the Initech renewal", "success": True},
                "continuation_comment": "now add the Initech pricing",
            }
        )
        provider = _provider(
            _workflow("Add Initech pricing to the draft: {{goal}}"),
            _workflow("Add the pricing to the draft: {{goal}}"),
        )
        result = await WorkflowCreatorAction().run(self._task("Add pricing"), context)
        assert result.success
        assert provider.complete.await_count == 2
        hit = result.output["leak_guard"]["hits"][0]
        assert (hit["text"], hit["source"]) == ("Initech", RUN)

    def test_prompt_states_the_rule(self):
        from zebra_tasks.agent.creator import WorkflowCreatorAction

        assert "Never copy names, companies" in WorkflowCreatorAction._PROMPT_FOOTER


class TestVariantCreator:
    def _task(self, goal: str) -> MagicMock:
        task = MagicMock()
        task.properties = {"goal": goal, "source_workflow_name": "Project Update"}
        return task

    async def test_names_in_the_source_are_allowed(self, context):
        from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction

        source = _workflow("Ask Acme Corp about the plan: {{goal}}")
        library = MagicMock()
        library.get_workflow_yaml = MagicMock(return_value=source)
        context.extras["__workflow_library__"] = library
        variant = _workflow("Ask Acme Corp about the plan in detail: {{goal}}", name="Detailed")
        provider = _provider(variant)

        result = await WorkflowVariantCreatorAction().run(
            self._task("Detailed plan for Acme Corp"), context
        )
        assert result.success
        assert provider.complete.await_count == 1

    async def test_goal_specifics_are_generalised(self, context):
        from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction

        library = MagicMock()
        library.get_workflow_yaml = MagicMock(return_value=ORIGINAL)
        context.extras["__workflow_library__"] = library
        provider = _provider(
            _workflow("Update Globex's plan: {{goal}}", name="Globex Update"),
            _workflow("Update the client's plan: {{goal}}", name="Client Update"),
        )
        result = await WorkflowVariantCreatorAction().run(
            self._task("Update the plan for Globex"), context
        )
        assert result.success
        assert provider.complete.await_count == 2
        assert "Globex" not in library.add_workflow.call_args.args[0]
        assert result.output["leak_guard"]["status"] == "generalised"

    def test_prompt_states_the_rule(self):
        from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction

        assert "Never copy names, companies" in WorkflowVariantCreatorAction.SYSTEM_PROMPT


async def test_evaluator_records_run_exposure(context):
    from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction

    _provider('{"overall_assessment": {"health_score": 80}, "improvement_priorities": []}')
    task = MagicMock()
    task.properties = {
        "metrics_analysis": {
            "failure_patterns": [
                {
                    "workflow_name": "Billing",
                    "failure_count": 1,
                    "sample_goals": ["Fix Jane's invoice"],
                }
            ],
            "continuation_analysis": {
                "total_continuations": 1,
                "frequently_continued": [
                    {
                        "workflow_name": "Billing",
                        "continuation_count": 1,
                        "comments": ["also email Bob"],
                    }
                ],
            },
        },
        "output_key": "evaluation",
    }
    result = await WorkflowEvaluatorAction().run(task, context)
    assert result.success
    assert result.output["run_exposure"] == ["Fix Jane's invoice", "also email Bob"]
