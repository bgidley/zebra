"""Integration tests for the ethics gates in the agent main loop workflow.

Verifies that the agent_main_loop.yaml correctly wires ethics checkpoints:
1. Input gate before workflow selection
2. Plan review before execution
3. Post-execution review with human confirmation
"""

from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import TaskAction
from zebra.tasks.registry import ActionRegistry

# ---------------------------------------------------------------------------
# Stub actions — replace real LLM calls with deterministic responses
# ---------------------------------------------------------------------------


class StubConsultMemory(TaskAction):
    async def run(self, task, context):
        output = {"shortlist": [], "memory_context": "", "has_memory": False}
        key = task.properties.get("output_key", "memory_shortlist")
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


class StubAssessAndRecord(TaskAction):
    async def run(self, task, context):
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


def _make_registry(ethics_gate_class):
    """Build a registry with stub actions and the given ethics gate class."""
    registry = ActionRegistry()
    registry.register_defaults()  # registers route_name condition
    registry.register_action("consult_memory", StubConsultMemory)
    registry.register_action("ethics_gate", ethics_gate_class)
    registry.register_action("workflow_selector", StubWorkflowSelector)
    registry.register_action("workflow_creator", StubWorkflowSelector)  # not reached
    registry.register_action("workflow_variant_creator", StubWorkflowSelector)  # not reached
    registry.register_action("execute_goal_workflow", StubExecuteWorkflow)
    registry.register_action("assess_and_record", StubAssessAndRecord)
    registry.register_action("llm_call", StubLLMCall)
    registry.register_action("update_conceptual_memory", StubUpdateConceptualMemory)
    return registry


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEthicsWorkflowIntegration:
    """Test the full agent main loop with ethics gates."""

    async def test_both_gates_approve_reaches_human_confirmation(self, definition):
        """When both ethics gates approve, flow reaches the human confirmation task."""
        registry = _make_registry(StubEthicsGateApprove)
        store = InMemoryStore()
        engine = WorkflowEngine(store, registry)

        process = await engine.create_process(
            definition,
            properties={"goal": "Write a poem", "available_workflows": []},
        )
        await engine.start_process(process.id)

        # Process should be waiting on the human confirmation task
        process = await store.load_process(process.id)
        assert process.state == ProcessState.RUNNING

        # There should be a pending human task (ethics_human_confirmation)
        pending = await engine.get_pending_tasks(process.id)
        assert len(pending) == 1
        task_instance = pending[0]
        assert task_instance.task_definition_id == "ethics_human_confirmation"

        # Complete the human task to finish the workflow
        await engine.complete_task(
            task_instance.id,
            TaskResult.ok(output={"confirmed": True, "human_concerns": ""}),
        )

        process = await store.load_process(process.id)
        assert process.state == ProcessState.COMPLETE

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
