import asyncio

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_golden_path_goal(authenticated_async_client, agent_loop):
    """
    Test the golden path: submit a goal, poll until complete, check output.
    """
    async_client = authenticated_async_client

    # 1. Submit goal
    response = await async_client.post(
        "/api/goals/", {"goal": "What is the capital of France?"}, content_type="application/json"
    )
    assert response.status_code == 202
    data = response.json()
    run_id = data["run_id"]
    status_url = data["status_url"]

    # 2. Poll for completion
    max_attempts = 120
    is_complete = False

    for _ in range(max_attempts):
        # We need to give the background task a chance to run.
        await asyncio.sleep(0.5)

        status_res = await async_client.get(status_url)
        assert status_res.status_code == 200
        status_data = status_res.json()

        if status_data["status"] in ("completed", "failed"):
            is_complete = True
            assert status_data["status"] == "completed"
            assert "paris" in str(status_data.get("output", "")).lower()
            break

    assert is_complete, "Goal did not complete within timeout"

    # 3. Check diagram endpoint
    diagram_url = f"/api/runs/{run_id}/diagram/"
    diagram_res = await async_client.get(diagram_url)
    assert diagram_res.status_code == 200
    diagram_data = diagram_res.json()
    assert "<svg" in diagram_data.get("svg", "")
