import asyncio

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_human_task_loop(async_client, workflow_engine, workflow_library):
    """
    Test the human task loop:
    1. Start a workflow that has an auto:false task
    2. Check the pending-tasks endpoint for the form schema
    3. Submit the form completion
    4. Ensure the workflow resumes and completes
    """
    # 1. Create a custom workflow with an auto:false task
    yaml_content = """
name: "Test Human Task"
description: "Test workflow"
tags: ["test"]
version: 1
first_task: ask_user

tasks:
  ask_user:
    name: "Ask User"
    auto: false
    properties:
      schema:
        type: object
        required: ["favorite_color"]
        properties:
          favorite_color:
            type: string

  finish:
    name: "Finish"
    auto: true
    action: python_exec
    properties:
      code: "result = {'color': '{{__task_output_ask_user.favorite_color}}'}"
      output_key: python_out
routings:
  - from: ask_user
    to: finish
"""
    workflow_name = workflow_library.add_workflow(yaml_content)
    definition = workflow_library.get_workflow(workflow_name)

    # 2. Start the process
    process = await workflow_engine.create_process(definition)
    await workflow_engine.start_process(process.id)

    # Give it a moment to reach the auto:false task
    await asyncio.sleep(0.2)

    # 3. Query pending tasks via API
    pending_res = await async_client.get(f"/api/processes/{process.id}/pending-tasks/")
    assert pending_res.status_code == 200
    pending_data = pending_res.json()
    assert len(pending_data) == 1

    task_id = pending_data[0]["id"]
    schema = pending_data[0]["definition"]["properties"]["schema"]
    assert schema["required"] == ["favorite_color"]

    # 4. Submit form completion
    complete_res = await async_client.post(
        f"/api/tasks/{task_id}/complete/",
        {"result": {"favorite_color": "blue"}},
        content_type="application/json",
    )
    assert complete_res.status_code == 200
    complete_data = complete_res.json()
    assert complete_data["completed"] is True

    # Give the engine a moment to route to the next task and finish
    for _ in range(10):
        await asyncio.sleep(0.2)
        proc_res = await async_client.get(f"/api/processes/{process.id}/")
        if proc_res.status_code == 200 and proc_res.json()["state"] == "complete":
            break

    # Verify the process is completed
    proc_res = await async_client.get(f"/api/processes/{process.id}/")
    assert proc_res.status_code == 200
    proc_data = proc_res.json()

    # Check task errors
    tasks_data = proc_data.get("tasks", [])
    for t in tasks_data:
        if t["state"] == "failed":
            print(f"Task {t['task_definition_id']} failed with error: {t.get('error')}")

    assert proc_data["state"] == "complete"

    # Verify the output property was set by the finish task
    ask_user_output = proc_data["properties"]["__task_output_ask_user"]
    assert ask_user_output["favorite_color"] == "blue"
    assert proc_data["properties"]["python_out"] == {"color": "blue"}
