"""Tests for the "I'm stuck" handoff actions (#176)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from zebra.core.models import (
    ProcessDefinition,
    ProcessInstance,
    TaskDefinition,
    TaskInstance,
)
from zebra.tasks.base import ExecutionContext

from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction
from zebra_tasks.agent.stuck import (
    HELP_DISPLAY_KEY,
    HELP_HISTORY_KEY,
    HELP_REQUESTS_KEY,
    ApplyHelpResponseAction,
    AssessStuckAction,
    with_help_guidance,
)
from zebra_tasks.llm.base import LLMResponse, TokenUsage

_DEF = ProcessDefinition(
    id="loop",
    name="Loop",
    first_task_id="t",
    tasks={"t": TaskDefinition(id="t", name="T")},
)


def _context(properties: dict) -> ExecutionContext:
    process = ProcessInstance(id="p1", definition_id="loop", properties=properties)
    return ExecutionContext(
        engine=MagicMock(),
        store=MagicMock(),
        process=process,
        process_definition=_DEF,
        task_definition=_DEF.tasks["t"],
    )


def _task(**properties) -> TaskInstance:
    return TaskInstance(
        id="t1", process_id="p1", task_definition_id="t", foe_id="f1", properties=properties
    )


def _assess_task(**overrides) -> TaskInstance:
    props = {
        "goal": "{{goal}}",
        "workflow_name": "{{workflow_name}}",
        "success": "{{execution_result.success}}",
        "error": "{{execution_result.error}}",
        "max_help_requests": 2,
    }
    props.update(overrides)
    return _task(**props)


def _failed_props(**extra) -> dict:
    return {
        "goal": "Plan my FIRE date",
        "workflow_name": "FIRE Calculator",
        "execution_result": {"success": False, "error": "NameError: fire_number"},
        "__task_executions__": [
            {"task_name": "Calculate", "state": "failed", "error": "NameError: fire_number"}
        ],
        **extra,
    }


def _provider(content: str) -> MagicMock:
    provider = MagicMock()
    provider.model = "claude-haiku-5-5"
    provider.complete = AsyncMock(
        return_value=LLMResponse(
            content=content,
            tool_calls=None,
            finish_reason="end_turn",
            model="claude-haiku-5-5",
            usage=TokenUsage(input_tokens=100, output_tokens=50),
        )
    )
    return provider


class TestAssessStuck:
    async def test_success_proceeds_without_llm(self):
        context = _context({"goal": "g", "execution_result": {"success": True}})
        with patch("zebra_tasks.agent.stuck.get_llm") as get_provider:
            result = await AssessStuckAction().run(_assess_task(), context)
        assert result.next_route == "proceed"
        get_provider.assert_not_called()
        assert HELP_REQUESTS_KEY not in context.process.properties

    async def test_failure_asks_human_with_llm_request(self):
        context = _context(_failed_props())
        reply = {
            "tried": "I ran the FIRE Calculator.",
            "stuck_on": "Its calculation step references an undefined variable.",
            "need": "Your current savings and yearly spend.",
            "voice": "I got stuck on the maths; can you give me your numbers?",
            "confidence": 0.7,
        }
        provider = _provider(json.dumps(reply))
        with patch("zebra_tasks.agent.stuck.get_llm", return_value=provider):
            result = await AssessStuckAction().run(_assess_task(), context)

        assert result.next_route == "ask_human"
        props = context.process.properties
        assert props[HELP_REQUESTS_KEY] == 1
        request = props["help_request"]
        assert request["need"] == "Your current savings and yearly spend."
        assert request["error"] == "NameError: fire_number"
        assert request["voice"].startswith("I got stuck")
        assert "Where I'm stuck: Its calculation step" in props[HELP_DISPLAY_KEY]
        assert props["__total_cost__"] > 0
        prompt = provider.complete.call_args.kwargs["messages"][1].content
        assert "Calculate [failed]: NameError" in prompt

    async def test_provider_error_falls_back_to_plain_request(self):
        context = _context(_failed_props())
        with patch("zebra_tasks.agent.stuck.get_llm", side_effect=RuntimeError("no key")):
            result = await AssessStuckAction().run(_assess_task(), context)
        assert result.success
        assert result.next_route == "ask_human"
        display = context.process.properties[HELP_DISPLAY_KEY]
        assert "FIRE Calculator" in display
        assert "NameError: fire_number" in display

    async def test_no_recorded_steps(self):
        context = _context(_failed_props(__task_executions__=[]))
        provider = _provider("{}")
        with patch("zebra_tasks.agent.stuck.get_llm", return_value=provider):
            result = await AssessStuckAction().run(_assess_task(), context)
        assert result.next_route == "ask_human"
        prompt = provider.complete.call_args.kwargs["messages"][1].content
        assert "(no steps recorded)" in prompt

    async def test_unparseable_reply_falls_back(self):
        context = _context(_failed_props())
        with patch("zebra_tasks.agent.stuck.get_llm", return_value=_provider("not json")):
            result = await AssessStuckAction().run(_assess_task(), context)
        assert result.next_route == "ask_human"
        assert "It failed: NameError" in context.process.properties[HELP_DISPLAY_KEY]

    async def test_budget_spent_proceeds(self):
        context = _context(_failed_props(**{HELP_REQUESTS_KEY: 2}))
        with patch("zebra_tasks.agent.stuck.get_llm") as get_provider:
            result = await AssessStuckAction().run(_assess_task(), context)
        assert result.next_route == "proceed"
        assert result.output["help_budget_spent"] is True
        get_provider.assert_not_called()
        assert context.process.properties[HELP_REQUESTS_KEY] == 2


class TestApplyHelpResponse:
    async def _apply(self, answer: dict, **extra) -> tuple:
        context = _context(_failed_props(__task_output_stuck_help_request=answer, **extra))
        result = await ApplyHelpResponseAction().run(_task(), context)
        return result, context.process.properties

    async def test_retry_records_guidance(self):
        result, props = await self._apply({"decision": "retry", "guidance": "Use 4% SWR"})
        assert result.next_route == "retry"
        assert props["goal"] == "Plan my FIRE date"
        assert props[HELP_HISTORY_KEY] == [
            {"error": "NameError: fire_number", "decision": "retry", "guidance": "Use 4% SWR"}
        ]

    async def test_redirect_replaces_goal(self):
        result, props = await self._apply({"decision": "redirect", "guidance": "Just a budget"})
        assert result.next_route == "redirect"
        assert props["goal"] == "Just a budget"
        assert props["original_goal"] == "Plan my FIRE date"
        assert props[HELP_HISTORY_KEY][0]["previous_goal"] == "Plan my FIRE date"

    async def test_second_redirect_keeps_first_original_goal(self):
        _, props = await self._apply(
            {"decision": "redirect", "guidance": "Third goal"}, original_goal="First goal"
        )
        assert props["original_goal"] == "First goal"

    async def test_empty_redirect_is_a_retry(self):
        result, props = await self._apply({"decision": "redirect", "guidance": "  "})
        assert result.next_route == "retry"
        assert props["goal"] == "Plan my FIRE date"

    async def test_abandon_marks_error(self):
        result, props = await self._apply({"decision": "abandon"})
        assert result.next_route == "abandon"
        assert props["execution_result"]["error"] == (
            "NameError: fire_number (abandoned after asking for help)"
        )

    async def test_missing_answer_abandons(self):
        result, _ = await self._apply({})
        assert result.next_route == "abandon"

    async def test_long_error_is_clipped_in_history(self):
        context = _context(
            {
                "goal": "g",
                "execution_result": {"success": False, "error": "x" * 5000},
                "__task_output_stuck_help_request": {"decision": "retry"},
            }
        )
        await ApplyHelpResponseAction().run(_task(), context)
        assert len(context.process.properties[HELP_HISTORY_KEY][0]["error"]) == 1000


class TestWithHelpGuidance:
    def test_no_history_leaves_goal(self):
        assert with_help_guidance("g", {}) == "g"

    def test_appends_retry_and_redirect_entries(self):
        props = {
            HELP_HISTORY_KEY: [
                {"error": "boom", "decision": "retry", "guidance": "try smaller"},
                {"error": "bang", "decision": "redirect", "previous_goal": "old goal"},
            ]
        }
        text = with_help_guidance("new goal", props)
        assert text.startswith("new goal\n")
        assert "Attempt 1 failed: boom" in text
        assert "User guidance: try smaller" in text
        assert "Attempt 2 failed: bang" in text
        assert "redirected the goal from: old goal" in text

    async def test_child_goal_carries_guidance(self):
        """execute_goal_workflow passes the help history to the child's goal."""
        context = _context(
            {
                "goal": "Plan my FIRE date",
                HELP_HISTORY_KEY: [{"error": "boom", "decision": "retry", "guidance": "4% SWR"}],
            }
        )
        context.engine.create_process = AsyncMock(
            return_value=ProcessInstance(id="child", definition_id="fire")
        )
        context.engine.start_process_with_timeout = AsyncMock()
        context.store.save_process = AsyncMock()
        context.store.save_task = AsyncMock()

        await ExecuteGoalWorkflowAction()._spawn_child(
            _task(), context, _DEF, "Plan my FIRE date", 60
        )

        goal = context.engine.create_process.call_args.kwargs["properties"]["goal"]
        assert goal.startswith("Plan my FIRE date")
        assert "User guidance: 4% SWR" in goal
