"""End-to-end integration tests for the agent main loop workflow.

These tests run against the real Oracle database and make real LLM API calls.
They verify the complete flow from goal input through workflow execution
to metrics and memory persistence.

The agent_main_loop.yaml workflow orchestrates:
1. Memory compaction check
2. Workflow selection via LLM
3. Workflow creation (if needed)
4. Workflow execution
5. Metrics recording
6. Memory updates

Prerequisites:
- Oracle database configured in .env (ORACLE_DSN, ORACLE_USERNAME, ORACLE_PASSWORD)
- ANTHROPIC_API_KEY configured in .env
- Database migrations applied (python manage.py migrate)

Note: Tests do NOT clean up after themselves - records persist in Oracle for inspection.
"""

import uuid

import pytest
from asgiref.sync import sync_to_async


@pytest.mark.asyncio
class TestAgentLoopIntegration:
    """Integration tests for agent_main_loop.yaml with Django/Oracle backend."""

    async def test_process_goal_selects_existing_workflow(self, agent_loop, django_stores):
        """Test processing a simple question uses Answer Question workflow.

        This test verifies:
        1. WorkflowSelectorAction correctly identifies a matching workflow
        2. The selected workflow executes successfully
        3. Metrics are recorded to Django/Oracle
        4. Memory entry is added to Django/Oracle
        """
        goal = "What is the capital of France?"

        result = await agent_loop.process_goal(goal)

        # Verify execution result
        assert result.success, f"Expected success but got error: {result.error}"
        assert result.workflow_name == "Answer Question", (
            f"Expected 'Answer Question' but got '{result.workflow_name}'"
        )
        assert result.output is not None
        # The answer should mention Paris
        output_str = str(result.output).lower()
        assert "paris" in output_str, f"Expected 'Paris' in output: {result.output}"
        assert result.created_new_workflow is False

        # Verify metrics recorded in Django
        runs = await django_stores.metrics.get_recent_runs(limit=5)
        assert len(runs) >= 1, "Expected at least one workflow run recorded"

        # Find our run
        our_run = next((r for r in runs if r.id == result.run_id), None)
        assert our_run is not None, f"Run {result.run_id} not found in recent runs"
        assert our_run.workflow_name == "Answer Question"
        assert our_run.success is True
        assert "capital" in our_run.goal.lower()

        # Verify memory entry in Django
        entries = await django_stores.memory.get_recent_workflow_memories(limit=5)
        assert len(entries) >= 1, "Expected at least one memory entry"

        # Find our entry (most recent should be ours)
        our_entry = next((e for e in entries if "capital" in e.goal.lower()), None)
        assert our_entry is not None, "Memory entry for our goal not found"
        assert our_entry.workflow_name == "Answer Question"

    async def test_process_goal_uses_brainstorm_for_ideas(self, agent_loop, django_stores):
        """Test that brainstorming requests use the Brainstorm Ideas workflow."""
        goal = "Give me 5 creative ideas for a birthday party theme"

        result = await agent_loop.process_goal(goal)

        assert result.success, f"Expected success but got error: {result.error}"
        # Should select Brainstorm Ideas based on the goal keywords
        # (though LLM might choose differently)
        assert result.workflow_name in ["Brainstorm Ideas", "Answer Question"], (
            f"Expected brainstorm-related workflow but got '{result.workflow_name}'"
        )
        assert result.output is not None
        # Should have multiple ideas in the output
        output_str = str(result.output)
        assert len(output_str) > 100, "Expected substantial output with ideas"

    async def test_process_goal_with_custom_run_id(self, agent_loop, django_stores):
        """Test that custom run_id is used for tracking."""
        custom_run_id = f"test-integration-{uuid.uuid4()}"
        goal = "What is 2 + 2?"

        result = await agent_loop.process_goal(goal, run_id=custom_run_id)

        assert result.success, f"Expected success but got error: {result.error}"
        assert result.run_id == custom_run_id

        # Verify run recorded with custom ID
        run = await django_stores.metrics.get_run(custom_run_id)
        assert run is not None, f"Run with ID {custom_run_id} not found"
        assert run.id == custom_run_id
        assert run.goal == goal

    async def test_process_goal_records_tokens_used(self, agent_loop, django_stores):
        """Test that token usage is tracked."""
        goal = "Explain photosynthesis in one sentence"

        result = await agent_loop.process_goal(goal)

        assert result.success, f"Expected success but got error: {result.error}"
        # Token usage should be tracked (may be 0 if provider doesn't report)
        assert result.tokens_used >= 0

        # Verify in database
        run = await django_stores.metrics.get_run(result.run_id)
        assert run is not None
        assert run.tokens_used >= 0

    async def test_multiple_goals_accumulate_memory(self, agent_loop, django_stores):
        """Test that multiple goals build up memory entries."""
        # Use a large limit to ensure we count all entries, not just the most recent 20
        large_limit = 10000
        initial_entries = await django_stores.memory.get_recent_workflow_memories(limit=large_limit)
        initial_count = len(initial_entries)

        goals = [
            "What is the speed of light?",
            "Who wrote Romeo and Juliet?",
            "What year did World War 2 end?",
        ]

        for goal in goals:
            result = await agent_loop.process_goal(goal)
            assert result.success, f"Failed on goal '{goal}': {result.error}"

        # Verify memory has accumulated
        final_entries = await django_stores.memory.get_recent_workflow_memories(limit=large_limit)
        final_count = len(final_entries)

        assert final_count >= initial_count + 3, (
            f"Expected at least 3 new entries, got {final_count - initial_count}"
        )


@pytest.mark.asyncio
class TestAgentLoopDatabasePersistence:
    """Tests focused on verifying Django/Oracle persistence."""

    async def test_workflow_run_persists_all_fields(self, agent_loop, django_stores):
        """Verify all WorkflowRun fields are persisted to Oracle."""
        from zebra_agent_web.api.models import WorkflowRunModel

        goal = "What color is the sky on a clear day?"

        result = await agent_loop.process_goal(goal)
        assert result.success, f"Expected success but got error: {result.error}"

        # Fetch directly from Django model
        @sync_to_async
        def get_run_model(run_id):
            return WorkflowRunModel.objects.get(id=run_id)

        run_model = await get_run_model(result.run_id)

        assert run_model.workflow_name == result.workflow_name
        assert run_model.goal == goal
        assert run_model.success == result.success
        assert run_model.started_at is not None
        assert run_model.completed_at is not None
        assert run_model.tokens_used >= 0
        # Output should be stored
        assert run_model.output is not None

    async def test_memory_entry_persists_all_fields(self, agent_loop, django_stores):
        """Verify all WorkflowMemory fields are persisted to Oracle."""
        from zebra_agent_web.api.models import WorkflowMemoryModel

        goal = "What is the largest planet in our solar system?"

        result = await agent_loop.process_goal(goal)
        assert result.success, f"Expected success but got error: {result.error}"

        # Fetch directly from Django model
        @sync_to_async
        def get_memory_entries(goal_fragment):
            return list(
                WorkflowMemoryModel.objects.filter(goal__icontains=goal_fragment).order_by(
                    "-timestamp"
                )[:5]
            )

        entries = await get_memory_entries("largest planet")

        assert len(entries) >= 1, "Memory entry not found in database"
        entry = entries[0]
        assert entry.workflow_name == result.workflow_name
        assert entry.tokens_used >= 0
        assert entry.output_summary is not None
        assert len(entry.output_summary) > 0


@pytest.mark.asyncio
class TestAgentLoopWorkflowCreation:
    """Tests for workflow creation scenarios."""

    async def test_process_novel_goal_may_create_workflow(self, agent_loop, django_stores):
        """Test that a highly specific/unusual goal may trigger workflow creation.

        Note: Whether the LLM chooses to create a new workflow or use an existing
        one is up to the LLM's judgment. This test verifies the flow works either way.
        """
        # Use a very specific/unusual goal
        goal = "Write a limerick about a programmer debugging code at 3am"

        result = await agent_loop.process_goal(goal)

        assert result.success, f"Expected success but got error: {result.error}"
        assert result.output is not None
        assert result.workflow_name is not None

        # If it created a new workflow, verify it's in the library
        if result.created_new_workflow:
            workflows = await agent_loop.library.list_workflows()
            workflow_names = [w.name for w in workflows]
            assert result.workflow_name in workflow_names, (
                f"Created workflow '{result.workflow_name}' not found in library"
            )
            print(f"New workflow created: {result.workflow_name}")
        else:
            print(f"Used existing workflow: {result.workflow_name}")

        # Either way, metrics should be recorded
        run = await django_stores.metrics.get_run(result.run_id)
        assert run is not None
        assert run.success is True


@pytest.mark.asyncio
class TestAgentLoopEdgeCases:
    """Tests for edge cases and error handling."""

    async def test_process_empty_goal(self, agent_loop, django_stores):
        """Test handling of empty goal.

        The LLM may handle this gracefully or fail - we just verify
        the system doesn't crash and records the attempt.
        """
        goal = ""

        await agent_loop.process_goal(goal)

        # May succeed or fail depending on LLM behavior
        # Either way, a run should be recorded
        runs = await django_stores.metrics.get_recent_runs(limit=1)
        assert len(runs) >= 1

    async def test_process_very_long_goal(self, agent_loop, django_stores):
        """Test handling of a very long goal text."""
        # Create a long but valid goal
        goal = "Please help me understand " + "the concept of " * 50 + "recursion in programming"

        result = await agent_loop.process_goal(goal)

        # Should handle long input gracefully
        assert result.success, f"Expected success but got error: {result.error}"
        assert result.output is not None

    async def test_process_goal_with_special_characters(self, agent_loop, django_stores):
        """Test handling of special characters in goal."""
        goal = "What does the equation E=mc^2 mean? (Einstein's famous formula)"

        result = await agent_loop.process_goal(goal)

        assert result.success, f"Expected success but got error: {result.error}"
        assert result.output is not None

        # Verify goal stored correctly in database
        run = await django_stores.metrics.get_run(result.run_id)
        assert run is not None
        assert "E=mc" in run.goal
