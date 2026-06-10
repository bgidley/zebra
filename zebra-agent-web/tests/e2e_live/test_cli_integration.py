"""Integration test for the zebra CLI against the real Oracle database (F34).

Issue #34 E2E criterion: a goal created via the CLI appears in the web
dashboard. The dashboard's activity view reads CREATED processes from the
same engine store, so queueing via the CLI handler and reading the process
back through that store proves the path without spending LLM budget.

Prerequisites: ORACLE_* variables in .env (loaded by pytest-dotenv).

Unlike the other e2e_live tests, this one cleans up the process it creates —
otherwise the budget daemon would pick it up and execute it.
"""

import uuid

import pytest
from asgiref.sync import sync_to_async


@pytest.mark.asyncio
class TestCliIntegration:
    async def test_cli_queued_goal_visible_in_dashboard_store(self, django_stores):
        """Queue a goal via the CLI handler; assert it lands in Oracle as CREATED."""
        from zebra.core.models import ProcessState
        from zebra_agent_web.cli import _goal_async

        marker = f"cli-integration-{uuid.uuid4().hex[:8]}"
        goal_text = f"Integration test goal {marker} — do not execute"

        process_id = None
        try:
            code = await _goal_async(goal_text, model="haiku", queue=True, priority=5)
            assert code == 0

            # The dashboard activity view reads CREATED processes from this store.
            created = await django_stores.store.get_processes_by_state(ProcessState.CREATED)
            ours = next(
                (p for p in created if marker in (p.properties or {}).get("goal", "")), None
            )
            assert ours is not None, "CLI-queued goal not found in CREATED processes"
            process_id = ours.id

            props = ours.properties
            assert props["priority"] == 5
            assert props["run_id"]
            assert props["__llm_model__"]  # haiku alias resolved
            assert props["available_workflows"]
        finally:
            if process_id:

                @sync_to_async(thread_sensitive=False)
                def _cleanup():
                    from zebra_agent_web.api.models import (
                        FlowOfExecutionModel,
                        ProcessInstanceModel,
                        TaskInstanceModel,
                    )

                    TaskInstanceModel.objects.filter(process_id=process_id).delete()
                    FlowOfExecutionModel.objects.filter(process_id=process_id).delete()
                    ProcessInstanceModel.objects.filter(id=process_id).delete()

                await _cleanup()
