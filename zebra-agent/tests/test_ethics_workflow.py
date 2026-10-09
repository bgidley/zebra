"""Integration tests for the ethics gates in the agent main loop workflow.

Verifies that the agent_main_loop.yaml correctly wires ethics checkpoints:
1. Input gate before workflow selection
2. Plan review before execution
3. Post-execution LLM review (automated, no human confirmation required)
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.agent.continuation_assessor import ContinuationAssessorAction
from zebra_tasks.agent.history import AssessHistoryNeedAction, GetWorkflowHistoryAction
from zebra_tasks.agent.propagate_failure import PropagateFailureAction
from zebra_tasks.agent.record_dilemma_resolution import RecordDilemmaResolutionAction
from zebra_tasks.agent.record_ethics_rejection import RecordEthicsRejectionAction
from zebra_tasks.agent.record_ethics_review import RecordEthicsReviewAction
from zebra_tasks.knowledge.apply_resolution import ApplyResolutionAction
from zebra_tasks.knowledge.extract import ExtractKnowledgeAction
from zebra_tasks.knowledge.store_learned import StoreLearnedKnowledgeAction
from zebra_tasks.llm.base import LLMResponse

from zebra_agent.knowledge import KnowledgeEntry
from zebra_agent.storage.memory import InMemoryPersonalKnowledgeStore

# ---------------------------------------------------------------------------
# Stub actions — replace real LLM calls with deterministic responses
# ---------------------------------------------------------------------------


class StubConsultMemory(TaskAction):
    async def run(self, task, context):
        output = {"shortlist": [], "memory_context": "", "has_memory": False}
        key = task.properties.get("output_key", "memory_shortlist")
        context.set_process_property(key, output)
        return TaskResult.ok(output=output)


class StubConsultKnowledge(TaskAction):
    async def run(self, task, context):
        output = {"knowledge": "", "has_knowledge": False}
        key = task.properties.get("output_key", "knowledge_context")
        context.set_process_property(key, output)
        return TaskResult.ok(output=output)


class StubEthicsGateApprove(TaskAction):
    """Ethics gate that always approves."""

    async def run(self, task, context):
        output = {"approved": True, "overall_reasoning": "Approved", "concerns": []}
        key = task.properties.get("output_key", "ethics_assessment")
        context.set_process_property(key, output)
        return TaskResult(success=True, output=output, next_route="proceed")


class StubEthicsGateReject(TaskAction):
    """Ethics gate that always rejects."""

    async def run(self, task, context):
        output = {
            "approved": False,
            "overall_reasoning": "Rejected on ethical grounds",
            "concerns": ["Violates categorical imperative"],
        }
        key = task.properties.get("output_key", "ethics_assessment")
        context.set_process_property(key, output)
        return TaskResult(success=True, output=output, next_route="reject")


class StubEthicsGateEscalate(TaskAction):
    """Input gate approves; plan-review escalates a dilemma (F22)."""

    async def run(self, task, context):
        key = task.properties.get("output_key", "ethics_assessment")
        if task.properties.get("check_type") == "plan_review":
            display = "Trade-off: honesty vs kindness\n• PROCEED: candid\n• DECLINE: gentle"
            output = {
                "approved": True,
                "overall_reasoning": "Permissible but values conflict",
                "concerns": [],
                "dilemma_display": display,
            }
            context.set_process_property(key, output)
            context.set_process_property("dilemma_display", display)
            return TaskResult(success=True, output=output, next_route="escalate")
        output = {"approved": True, "overall_reasoning": "Approved", "concerns": []}
        context.set_process_property(key, output)
        return TaskResult(success=True, output=output, next_route="proceed")


class StubWorkflowSelector(TaskAction):
    async def run(self, task, context):
        output = {
            "workflow_name": "Test Workflow",
            "create_new": False,
            "create_variant": False,
            "reasoning": "Exact match",
        }
        key = task.properties.get("output_key", "selection")
        context.set_process_property(key, output)
        context.set_process_property("workflow_name", "Test Workflow")
        return TaskResult(success=True, output=output, next_route="use_existing")


class StubFlagConcerns(TaskAction):
    """Advisory concern flagging — never blocks, flags one sample concern."""

    async def run(self, task, context):
        output = {
            "concerns": [
                {
                    "description": "Plan includes a potentially risky step",
                    "severity": "medium",
                    "step": "execute",
                }
            ],
            "summary": "One medium-severity concern flagged.",
        }
        key = task.properties.get("output_key", "planning_concerns")
        context.set_process_property(key, output)
        return TaskResult.ok(output=output)


class StubExecuteWorkflow(TaskAction):
    async def run(self, task, context):
        output = {
            "success": True,
            "output": "Task completed",
            "tokens_used": 100,
            "input_tokens": 60,
            "output_tokens": 40,
            "cost": 0.01,
        }
        key = task.properties.get("output_key", "execution_result")
        context.set_process_property(key, output)
        return TaskResult.ok(output=output)


class StubExecuteWorkflowFails(TaskAction):
    """Goal workflow failed; recorded as data (continue_on_failure), as the real action does."""

    async def run(self, task, context):
        assert task.properties.get("continue_on_failure") is True
        output = {"success": False, "output": None, "tokens_used": 5, "error": "boom"}
        key = task.properties.get("output_key", "execution_result")
        context.set_process_property(key, output)
        return TaskResult.ok(output=output)


class StubAssessAndRecord(TaskAction):
    async def run(self, task, context):
        context.set_process_property(
            "assessed_with",
            {
                "success": context.resolve_template(task.properties["success"]),
                "error": context.resolve_template(task.properties["error"]),
            },
        )
        output = {"recorded": True, "effectiveness_notes": "Effective execution."}
        key = task.properties.get("output_key", "assess_result")
        context.set_process_property(key, output)
        return TaskResult.ok(output=output)


class StubLLMCall(TaskAction):
    async def run(self, task, context):
        output = {"ethical": True, "overall_reasoning": "Ethical conduct confirmed."}
        key = task.properties.get("output_key", "llm_response")
        context.set_process_property(key, output)
        return TaskResult.ok(output={"response": output})


class StubUpdateConceptualMemory(TaskAction):
    async def run(self, task, context):
        output = {"updated": True}
        key = task.properties.get("output_key", "conceptual_memory_update")
        context.set_process_property(key, output)
        return TaskResult.ok(output=output)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

WORKFLOW_YAML_PATH = Path(__file__).parent.parent / "workflows" / "agent_main_loop.yaml"


@pytest.fixture
def definition():
    """Load the real agent_main_loop.yaml."""
    with open(WORKFLOW_YAML_PATH) as f:
        return load_definition_from_yaml(f.read())


def _make_registry(ethics_gate_class, execute_class=None):
    """Build a registry with stub actions and the given ethics gate class."""
    registry = ActionRegistry()
    registry.register_defaults()  # registers route_name condition
    registry.register_action("consult_memory", StubConsultMemory)
    registry.register_action("consult_knowledge", StubConsultKnowledge)
    registry.register_action("ethics_gate", ethics_gate_class)
    # F135: real assessor — passes non-continuation goals straight through (no LLM)
    registry.register_action("continuation_assessor", ContinuationAssessorAction)
    # F138: real history actions — goals without history cues skip the LLM
    registry.register_action("assess_history_need", AssessHistoryNeedAction)
    registry.register_action("get_workflow_history", GetWorkflowHistoryAction)
    registry.register_action("flag_concerns", StubFlagConcerns)
    registry.register_action("record_dilemma_resolution", RecordDilemmaResolutionAction)
    registry.register_action("workflow_selector", StubWorkflowSelector)
    registry.register_action("workflow_creator", StubWorkflowSelector)  # not reached
    registry.register_action("workflow_variant_creator", StubWorkflowSelector)  # not reached
    registry.register_action("execute_goal_workflow", execute_class or StubExecuteWorkflow)
    registry.register_action("assess_and_record", StubAssessAndRecord)
    registry.register_action("llm_call", StubLLMCall)
    registry.register_action("update_conceptual_memory", StubUpdateConceptualMemory)
    registry.register_action("propagate_failure", PropagateFailureAction)
    registry.register_action("record_ethics_review", RecordEthicsReviewAction)
    registry.register_action("record_ethics_rejection", RecordEthicsRejectionAction)
    # F152: real knowledge learning — skips without __user_id__ (no LLM call)
    registry.register_action("extract_knowledge", ExtractKnowledgeAction)
    registry.register_action("store_learned_knowledge", StoreLearnedKnowledgeAction)
    registry.register_action("apply_resolution", ApplyResolutionAction)
    return registry


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEthicsWorkflowIntegration:
    """Test the full agent main loop with ethics gates."""

    async def test_both_gates_approve_completes_workflow(self, definition):
        """When both ethics gates approve, flow runs through the LLM review and completes."""
        registry = _make_registry(StubEthicsGateApprove)
        store = InMemoryStore()
        engine = WorkflowEngine(store, registry)

        process = await engine.create_process(
            definition,
            properties={"goal": "Write a poem", "available_workflows": []},
        )
        await engine.start_process(process.id)

        # Process completes automatically — no human confirmation step required
        process = await store.load_process(process.id)
        assert process.state == ProcessState.COMPLETE

        # No pending human tasks
        pending = await engine.get_pending_tasks(process.id)
        assert len(pending) == 0

    async def test_failed_goal_workflow_is_recorded_then_fails_process(self, definition):
        """#140: a failed goal run still runs assess/learn, then the loop ends FAILED."""
        registry = _make_registry(StubEthicsGateApprove, StubExecuteWorkflowFails)
        store = InMemoryStore()
        engine = WorkflowEngine(store, registry)

        process = await engine.create_process(
            definition,
            properties={"goal": "Write a poem", "available_workflows": []},
        )
        await engine.start_process(process.id)

        process = await store.load_process(process.id)
        assert process.properties["assessed_with"] == {"success": "False", "error": "boom"}
        assert process.properties["ethics_post_assessment"] is not None
        assert process.properties["conceptual_memory_update"] == {"updated": True}
        assert process.state == ProcessState.FAILED
        assert process.properties["__error__"] == "boom"
        assert process.properties["__failed_task__"] == "report_outcome"

    async def test_concerns_flagged_during_planning(self, definition):
        """flag_concerns runs in the planning phase and records concerns on the process."""
        registry = _make_registry(StubEthicsGateApprove)
        store = InMemoryStore()
        engine = WorkflowEngine(store, registry)

        process = await engine.create_process(
            definition,
            properties={"goal": "Clean up files", "available_workflows": []},
        )
        await engine.start_process(process.id)

        process = await store.load_process(process.id)
        # planning_concerns is populated (advisory step ran before the gate)
        concerns = process.properties.get("planning_concerns")
        assert concerns is not None
        assert concerns["concerns"][0]["severity"] == "medium"
        # The advisory step did not block — flow completed all the way through
        assert process.state == ProcessState.COMPLETE

    async def test_dilemma_escalation_pauses_then_proceeds(self, definition):
        """An escalated dilemma pauses on a human task; resolving 'proceed' runs the plan."""
        registry = _make_registry(StubEthicsGateEscalate)
        store = InMemoryStore()
        engine = WorkflowEngine(store, registry)

        process = await engine.create_process(
            definition,
            properties={"goal": "Give honest feedback", "available_workflows": []},
        )
        await engine.start_process(process.id)

        # Workflow pauses on the dilemma resolution human task
        pending = await engine.get_pending_tasks(process.id)
        assert len(pending) == 1
        assert pending[0].task_definition_id == "ethics_dilemma_resolution"

        # The dilemma (both sides) is available to render
        process = await store.load_process(process.id)
        assert (
            "honesty vs kindness" in process.properties["ethics_plan_assessment"]["dilemma_display"]
        )

        # Human resolves: proceed
        await engine.complete_task(
            pending[0].id,
            TaskResult.ok(output={"decision": "proceed", "note": "I value candour"}),
        )

        process = await store.load_process(process.id)
        resolution = process.properties.get("dilemma_resolution")
        assert resolution["decision"] == "proceed"
        # Flow completed all the way through the post-execution LLM review
        assert process.state == ProcessState.COMPLETE

    async def test_dilemma_escalation_decline_stops_at_rejection(self, definition):
        """Resolving an escalated dilemma with 'decline' routes to ethics_rejection."""
        registry = _make_registry(StubEthicsGateEscalate)
        store = InMemoryStore()
        engine = WorkflowEngine(store, registry)

        process = await engine.create_process(
            definition,
            properties={"goal": "Give honest feedback", "available_workflows": []},
        )
        await engine.start_process(process.id)

        pending = await engine.get_pending_tasks(process.id)
        assert pending[0].task_definition_id == "ethics_dilemma_resolution"

        await engine.complete_task(
            pending[0].id,
            TaskResult.ok(output={"decision": "decline", "note": "not worth the cost"}),
        )

        process = await store.load_process(process.id)
        assert process.state == ProcessState.COMPLETE
        assert process.properties.get("dilemma_resolution")["decision"] == "decline"
        rejection = process.properties["ethics_rejection"]
        assert rejection["gate"] == "dilemma_resolution"
        assert "not worth the cost" in rejection["reasoning"]

    async def test_process_goal_reports_awaiting_input_on_dilemma(self, definition):
        """process_goal returns awaiting_input (not a timeout) when parked on the dilemma (#141)."""
        from zebra_agent.loop import AgentLoop

        engine = WorkflowEngine(InMemoryStore(), _make_registry(StubEthicsGateEscalate))
        library = MagicMock()
        library.get_workflow.return_value = definition
        library.list_workflows = AsyncMock(return_value=[])
        events = []

        async def progress(event, data):
            events.append((event, data))

        loop = AgentLoop(library=library, engine=engine, metrics=MagicMock())
        result = await loop.process_goal("Give honest feedback", progress_callback=progress)

        assert result.awaiting_input is True
        assert result.success is False
        assert "Awaiting human input: Resolve Ethics Dilemma" in result.error
        pending = [d for e, d in events if e == "human_task_pending"]
        assert len(pending) == 1
        assert pending[0]["task_definition_id"] == "ethics_dilemma_resolution"

    async def test_input_gate_rejects_stops_at_rejection(self, definition):
        """When input gate rejects, process completes at ethics_rejection."""
        registry = _make_registry(StubEthicsGateReject)
        store = InMemoryStore()
        engine = WorkflowEngine(store, registry)

        process = await engine.create_process(
            definition,
            properties={"goal": "Do something unethical", "available_workflows": []},
        )
        await engine.start_process(process.id)

        process = await store.load_process(process.id)
        assert process.state == ProcessState.COMPLETE

        # The ethics assessment should be recorded
        assert process.properties.get("ethics_input_assessment") is not None
        assert process.properties["ethics_input_assessment"]["approved"] is False
        assert process.properties["ethics_rejection"] == {
            "gate": "input_gate",
            "reasoning": "Rejected on ethical grounds",
            "concerns": ["Violates categorical imperative"],
        }

    async def test_plan_review_rejects_after_selection(self, definition):
        """When plan review rejects (but input gate approves), stops at rejection."""

        class ApproveInputRejectPlan(TaskAction):
            """Approves input_gate, rejects plan_review."""

            _call_count = 0

            async def run(self, task, context):
                check_type = task.properties.get("check_type", "input_gate")
                key = task.properties.get("output_key", "ethics_assessment")

                if check_type == "input_gate":
                    output = {"approved": True, "overall_reasoning": "OK", "concerns": []}
                    context.set_process_property(key, output)
                    return TaskResult(success=True, output=output, next_route="proceed")
                else:
                    output = {
                        "approved": False,
                        "overall_reasoning": "Plan is unethical",
                        "concerns": ["Workflow exploits resources"],
                    }
                    context.set_process_property(key, output)
                    return TaskResult(success=True, output=output, next_route="reject")

        registry = _make_registry(ApproveInputRejectPlan)
        store = InMemoryStore()
        engine = WorkflowEngine(store, registry)

        process = await engine.create_process(
            definition,
            properties={"goal": "Goal with bad plan", "available_workflows": []},
        )
        await engine.start_process(process.id)

        process = await store.load_process(process.id)
        assert process.state == ProcessState.COMPLETE

        # Input gate approved but plan review rejected
        assert process.properties.get("ethics_input_assessment", {}).get("approved") is True
        assert process.properties.get("ethics_plan_assessment", {}).get("approved") is False
        assert process.properties["ethics_rejection"]["gate"] == "plan_review"
        assert process.properties["ethics_rejection"]["reasoning"] == "Plan is unethical"

    async def test_ethics_assessment_recorded_in_properties(self, definition):
        """Ethics assessments are stored in process properties for traceability."""
        registry = _make_registry(StubEthicsGateApprove)
        store = InMemoryStore()
        engine = WorkflowEngine(store, registry)

        process = await engine.create_process(
            definition,
            properties={"goal": "Analyze data", "available_workflows": []},
        )
        await engine.start_process(process.id)

        process = await store.load_process(process.id)

        # Both ethics assessments should be stored
        assert "ethics_input_assessment" in process.properties
        assert "ethics_plan_assessment" in process.properties
        assert process.properties["ethics_input_assessment"]["approved"] is True
        assert process.properties["ethics_plan_assessment"]["approved"] is True


class TestEthicsOutcomeRecording:
    """Post-execution review is audited; memory update doesn't depend on it (#143)."""

    async def test_post_review_is_recorded_to_audit_trail(self, definition):
        audit = MagicMock()
        audit.append = AsyncMock()
        registry = _make_registry(StubEthicsGateApprove)
        store = InMemoryStore()
        engine = WorkflowEngine(store, registry, extras={"__ethics_audit_store__": audit})

        process = await engine.create_process(
            definition, properties={"goal": "Write a poem", "available_workflows": []}
        )
        await engine.start_process(process.id)

        process = await store.load_process(process.id)
        assert process.state == ProcessState.COMPLETE
        assert process.properties["ethics_post_assessment"] == {
            "ethical": True,
            "overall_reasoning": "Ethical conduct confirmed.",
            "concerns": [],
            "recommendations": [],
        }
        assert "ethics_rejection" not in process.properties
        # Gates are stubbed here, so the post-review recorder is the only auditor.
        check_types = [c.args[0].check_type for c in audit.append.await_args_list]
        assert check_types == ["post_review"]

    async def test_failed_post_review_does_not_skip_memory_update(self, definition):
        class FailingLLMCall(TaskAction):
            async def run(self, task, context):
                return TaskResult.fail("LLM unavailable")

        registry = _make_registry(StubEthicsGateApprove)
        registry.register_action("llm_call", FailingLLMCall)
        store = InMemoryStore()
        engine = WorkflowEngine(store, registry)

        process = await engine.create_process(
            definition, properties={"goal": "Write a poem", "available_workflows": []}
        )
        await engine.start_process(process.id)

        process = await store.load_process(process.id)
        assert process.properties["conceptual_memory_update"] == {"updated": True}
        assert "__task_output_record_ethics_review" not in process.properties


# ---------------------------------------------------------------------------
# F135: continuation assessment routing through the real main loop
# ---------------------------------------------------------------------------


class _Library:
    """WorkflowLibrary stand-in: knows only the given workflow names."""

    def __init__(self, names):
        self._names = set(names)

    def get_workflow(self, name):
        if name not in self._names:
            raise ValueError(name)
        return name


def _llm_returning(payload: dict):
    response = MagicMock()
    response.content = json.dumps(payload)
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=response)
    return provider


_PREVIOUS = {
    "run_id": "run-prev",
    "goal": "Draft a blog post",
    "workflow_name": "Writer",
    "success": True,
    "output": "Draft v1",
}


class TestContinuationRouting:
    """The assessor sits between the input gate and selection (F135)."""

    async def _run(self, definition, properties, provider=None, library=("Writer",)):
        registry = _make_registry(StubEthicsGateApprove)
        store = InMemoryStore()
        engine = WorkflowEngine(store, registry, extras={"__workflow_library__": _Library(library)})
        process = await engine.create_process(definition, properties=properties)
        with patch(
            "zebra_tasks.agent.continuation_assessor.get_provider",
            return_value=provider or _llm_returning({}),
        ) as get_provider:
            await engine.start_process(process.id)
        process = await store.load_process(process.id)
        assert process.state == ProcessState.COMPLETE
        return process.properties, get_provider

    async def test_non_continuation_goal_bypasses_assessment(self, definition):
        props, get_provider = await self._run(
            definition, {"goal": "Write a poem", "available_workflows": []}
        )
        get_provider.assert_not_called()
        assert "continuation_decision" not in props
        assert "__task_output_select_workflow" in props
        assert props["workflow_name"] == "Test Workflow"

    async def test_same_workflow_skips_selection(self, definition):
        provider = _llm_returning({"decision": "same_workflow", "rationale": "One more pass"})
        props, _ = await self._run(
            definition,
            {"goal": "Polish it", "available_workflows": [], "previous_run_context": _PREVIOUS},
            provider,
        )
        assert props["continuation_decision"] == "same_workflow"
        assert props["continuation_rationale"] == "One more pass"
        assert "__task_output_select_workflow" not in props
        assert props["workflow_name"] == "Writer"
        assert "__task_output_execute_workflow" in props

    async def test_existing_workflow_runs_selector(self, definition):
        provider = _llm_returning({"decision": "existing_workflow", "rationale": "Needs review"})
        props, _ = await self._run(
            definition,
            {"goal": "Review it", "available_workflows": [], "previous_run_context": _PREVIOUS},
            provider,
        )
        assert props["continuation_decision"] == "existing_workflow"
        assert "__task_output_select_workflow" in props
        assert "__task_output_create_workflow" not in props

    async def test_new_workflow_runs_creator(self, definition):
        provider = _llm_returning(
            {"decision": "new_workflow", "rationale": "Novel", "suggested_name": "Publisher"}
        )
        props, _ = await self._run(
            definition,
            {"goal": "Publish it", "available_workflows": [], "previous_run_context": _PREVIOUS},
            provider,
        )
        assert props["continuation_decision"] == "new_workflow"
        assert "__task_output_select_workflow" not in props
        assert "__task_output_create_workflow" in props

    async def test_same_workflow_missing_falls_back_to_selector(self, definition):
        provider = _llm_returning({"decision": "same_workflow", "rationale": "Again"})
        props, _ = await self._run(
            definition,
            {"goal": "Polish it", "available_workflows": [], "previous_run_context": _PREVIOUS},
            provider,
            library=(),
        )
        assert props["continuation_decision"] == "existing_workflow"
        assert "__task_output_select_workflow" in props


# ---------------------------------------------------------------------------
# F138: workflow history routing through the real main loop
# ---------------------------------------------------------------------------


class EchoGoal(TaskAction):
    """Child workflow task: records the goal it was given as its result."""

    async def run(self, task, context):
        context.set_process_property("answer", context.get_process_property("goal"))
        return TaskResult.ok(output="done")


class _ChildLibrary:
    """Library returning a one-task child workflow for 'Test Workflow'."""

    def get_workflow(self, name):
        from zebra.core.models import ProcessDefinition, TaskDefinition

        assert name == "Test Workflow"
        return ProcessDefinition(
            id="echo_wf",
            name="Test Workflow",
            first_task_id="echo",
            properties={"result_key": "answer"},
            tasks={"echo": TaskDefinition(id="echo", name="Echo", action="echo_goal")},
        )


class TestHistoryRouting:
    """assess_history_need → [get_workflow_history] → ethics_input_gate (F138)."""

    async def _run(self, definition, goal, provider=None):
        from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction

        from zebra_agent.metrics import WorkflowRun
        from zebra_agent.storage import InMemoryMetricsStore

        metrics = InMemoryMetricsStore()
        past = WorkflowRun.create("Research", "Compare pension providers")
        past.success = True
        past.output = "Vanguard has the lowest fees"
        await metrics.record_run(past)

        registry = _make_registry(StubEthicsGateApprove)
        registry.register_action("execute_goal_workflow", ExecuteGoalWorkflowAction)
        registry.register_action("echo_goal", EchoGoal)
        store = InMemoryStore()
        engine = WorkflowEngine(
            store,
            registry,
            extras={"__workflow_library__": _ChildLibrary(), "__metrics_store__": metrics},
        )
        process = await engine.create_process(
            definition, properties={"goal": goal, "available_workflows": []}
        )
        with patch(
            "zebra_tasks.agent.history.get_provider",
            return_value=provider or _llm_returning({}),
        ) as get_provider:
            await engine.start_process(process.id)
        process = await store.load_process(process.id)
        assert process.state == ProcessState.COMPLETE
        return process.properties, get_provider

    async def test_needs_history_reaches_child_goal(self, definition):
        provider = _llm_returning({"needs_history": True, "since": "-7d", "text": "pension"})
        props, _ = await self._run(
            definition, "What did I ask you about pensions last week?", provider
        )
        assert props["history_need"]["needs_history"] is True
        assert props["workflow_history"]["count"] == 1
        child_goal = props["execution_result"]["output"]
        assert child_goal.startswith("What did I ask you about pensions last week?")
        assert "<workflow_history>" in child_goal
        assert "Vanguard has the lowest fees" in child_goal

    async def test_no_history_leaves_goal_untouched(self, definition):
        props, get_provider = await self._run(definition, "Write a poem")
        get_provider.assert_not_called()
        assert "__task_output_get_workflow_history" not in props
        assert "workflow_history" not in props
        assert props["execution_result"]["output"] == "Write a poem"


# ---------------------------------------------------------------------------
# F152: the main loop learns personal knowledge from goal runs
# ---------------------------------------------------------------------------


class _ResolveLibrary:
    def get_workflow(self, name):
        path = WORKFLOW_YAML_PATH.parent / "resolve_contradiction.yaml"
        return load_definition_from_yaml(path.read_text())


def _extraction_provider(*candidates):
    provider = MagicMock()
    provider.complete = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps({"candidates": list(candidates)}),
            model="haiku",
            usage={},
            tool_calls=[],
            finish_reason="end_turn",
        )
    )
    return provider


class TestKnowledgeLearning:
    """Goal runs feed the personal knowledge store (F152)."""

    @staticmethod
    async def _run_goal(definition, knowledge, goal, user_id=1, provider=None):
        store = InMemoryStore()
        engine = WorkflowEngine(
            store,
            _make_registry(StubEthicsGateApprove),
            extras={"__knowledge_store__": knowledge, "__workflow_library__": _ResolveLibrary()},
        )
        props = {"goal": goal, "available_workflows": []}
        if user_id is not None:
            props["__user_id__"] = user_id
        process = await engine.create_process(definition, properties=props)
        with patch(
            "zebra_tasks.knowledge.extract.get_provider",
            return_value=provider or _extraction_provider(),
        ) as gp:
            await engine.start_process(process.id)
        return engine, await store.load_process(process.id), gp

    async def test_personal_fact_creates_agent_entry(self, definition):
        knowledge = InMemoryPersonalKnowledgeStore()
        provider = _extraction_provider(
            {"category": "facts", "key": "Employer", "value": "Acme", "confidence": 0.9}
        )
        _, process, _ = await self._run_goal(
            definition, knowledge, "I work at Acme, plan my commute", provider=provider
        )

        assert process.state == ProcessState.COMPLETE
        [entry] = await knowledge.get_entries(1)
        assert (entry.key, entry.value, entry.source) == ("employer", "Acme", "agent")
        assert entry.confidence < 1.0
        assert process.properties["learned_knowledge"]["stored"][0]["key"] == "employer"

    async def test_conflicting_fact_starts_resolution_without_overwrite(self, definition):
        knowledge = InMemoryPersonalKnowledgeStore()
        await knowledge.add_entry(
            KnowledgeEntry.create(user_id=1, category="facts", key="employer", value="Acme")
        )
        provider = _extraction_provider(
            {"category": "facts", "key": "employer", "value": "Globex", "confidence": 0.9}
        )
        engine, process, _ = await self._run_goal(
            definition, knowledge, "I now work at Globex", provider=provider
        )

        assert process.state == ProcessState.COMPLETE
        [entry] = await knowledge.get_entries(1)
        assert entry.value == "Acme" and entry.source == "human"
        [conflict] = process.properties["learned_knowledge"]["contradictions"]
        resolve = await engine.store.load_process(conflict["resolution_process_id"])
        assert resolve.state == ProcessState.RUNNING
        assert resolve.properties["proposed_value"] == "Globex"

    async def test_no_user_writes_nothing_and_skips_llm(self, definition):
        knowledge = InMemoryPersonalKnowledgeStore()
        _, process, gp = await self._run_goal(definition, knowledge, "I work at Acme", user_id=None)
        assert process.state == ProcessState.COMPLETE
        gp.assert_not_called()
        assert await knowledge.get_entries(1) == []

    async def test_nothing_personal_writes_nothing(self, definition):
        knowledge = InMemoryPersonalKnowledgeStore()
        _, process, gp = await self._run_goal(definition, knowledge, "Summarise this text")
        assert process.state == ProcessState.COMPLETE
        gp.assert_called_once()
        assert await knowledge.get_entries(1) == []
        assert "learned_knowledge" not in process.properties
