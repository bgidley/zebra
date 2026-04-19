import asyncio
import pytest
from django.urls import reverse
from unittest.mock import MagicMock

from zebra.core.models import ProcessState
from zebra_agent_web.api.daemon import _tick

pytestmark = pytest.mark.e2e

@pytest.mark.django_db
@pytest.mark.asyncio
async def test_budget_exhaustion_pauses_daemon(workflow_engine, workflow_library, django_stores):
    """
    Test that the daemon pauses new goals when the daily budget is hit.
    """
    from zebra_agent_web.api import agent_engine
    await agent_engine.ensure_initialized()
    
    budget_manager = agent_engine.get_budget_manager()
    # Force budget to be 0
    budget_manager.daily_budget_usd = 0.0
    
    # Create a test workflow
    yaml_content = """
name: "Budget Test"
description: "Test workflow"
tags: ["test"]
version: 1
first_task: finish

tasks:
  finish:
    name: "Finish"
    auto: true
    action: python_exec
    properties:
      code: "result = 'done'"
"""
    workflow_name = workflow_library.add_workflow(yaml_content)
    definition = workflow_library.get_workflow(workflow_name)
    
    # Queue the goal (create process without starting it)
    process = await workflow_engine.create_process(definition, properties={"goal": "test goal"})
    assert process.state == ProcessState.CREATED
    
    # Run one tick of the daemon
    from zebra_agent.scheduler import GoalScheduler
    scheduler = GoalScheduler(workflow_engine.store)
    
    # We should intercept the logger to check for the warning
    import logging
    import io
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    logger = logging.getLogger("zebra_agent_web.api.daemon")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    
    await _tick(
        scheduler=scheduler,
        budget_manager=budget_manager,
        engine=workflow_engine,
        dry_run=False,
    )
    
    # Process should still be in CREATED state because budget is exhausted
    updated_process = await workflow_engine.store.load_process(process.id)
    assert updated_process.state == ProcessState.CREATED
    
    # Check the logs for the warning
    log_output = log_capture.getvalue()
    assert "Budget exhausted" in log_output
    
    # Now increase budget and run tick again to verify it picks it up
    budget_manager.daily_budget_usd = 100.0
    await _tick(
        scheduler=scheduler,
        budget_manager=budget_manager,
        engine=workflow_engine,
        dry_run=False,
    )
    
    # Process should be complete now
    updated_process = await workflow_engine.store.load_process(process.id)
    assert updated_process.state == ProcessState.COMPLETE
