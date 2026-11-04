"""Judged Commons import through the web, end to end (Commons S3, #230).

The owner uploads a signed workflow file on ``/commons/``; *Commons Import* runs on the
Django store; the owner (and only the owner) approves the trust-gate task through the
task API; the workflow lands in the library supervised, and its first goal run and a
routine start both raise the pre-run approval. A file with personal data in a prompt is
rejected with a reason and nothing is saved; a file using ``file_delete`` never runs in
the gym and escalates. The LLM is faked (see ``_FakeLLM``); everything else is real.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from zebra.core.models import ProcessState
from zebra.definitions.loader import load_definition_from_yaml
from zebra_agent.commons import keys
from zebra_agent.commons.export import export_workflow
from zebra_agent.commons.identity import make_device_cert
from zebra_agent.library import WorkflowLibrary
from zebra_agent.scheduler.loop import SchedulerLoop
from zebra_agent.scheduler.registry import RoutineRegistry
from zebra_agent.scheduler.routine import Routine, RoutineRun
from zebra_agent.scheduler.store import InMemoryRoutineRunStore
from zebra_agent.scheduler.testing import FakeClock
from zebra_tasks.commons.supervised import APPROVAL_TASK, SUPERVISED_LAUNCH_KEY
from zebra_tasks.llm.base import LLMResponse, TokenUsage
from zebra_tasks.llm.client import set_llm_factory

pytestmark = pytest.mark.e2e

LOCAL_NAME = "Capital Facts (from Pub Zebra)"
GOLDEN = [{"goal": "Capital of Australia?", "expected": "Canberra", "criteria": ["Canberra"]}]


def _workflow(prompt: str = "Answer: {{goal}}", extra: str = "") -> str:
    return f"""name: "Capital Facts"
description: "Answer questions about capital cities"
tags: [facts]
version: 1
first_task: answer
tasks:
  answer:
    name: "Answer"
    action: llm_call
    properties:
      prompt: "{prompt}"
      output_key: answer
{extra}
routings: []
"""


class _FakeLLM:
    model = "fake"

    async def complete(self, messages, **kwargs) -> LLMResponse:
        system = messages[0].content if messages[0].role == "system" else ""
        user = messages[-1].content
        if "Find personal data" in system:
            content = '{"personal_data": false, "findings": []}'
        elif "grade the output of an AI workflow" in system:
            score = 1 if "Canberra" in user.split("## Workflow output", 1)[1] else 0
            content = json.dumps({"criteria": [{"criterion": 1, "score": score}]})
        elif "Kant" in system or "ethic" in system.lower():
            content = '{"approved": true, "overall_reasoning": "Harmless.", "concerns": []}'
        else:
            content = "Canberra"
        return LLMResponse(content, None, "stop", TokenUsage(10, 5), "fake")


@pytest.fixture
def commons_on(settings, tmp_path):
    settings.ZEBRA_AGENT_SETTINGS = {
        **settings.ZEBRA_AGENT_SETTINGS,
        "COMMONS_ENABLED": True,
        "COMMONS_KEY_DIR": str(tmp_path / "keys"),
    }
    set_llm_factory(lambda model: _FakeLLM())
    return settings


@pytest.fixture
def web(monkeypatch, workflow_engine, workflow_library, django_stores, commons_on):
    """Point the web app's engine and library at the test ones."""
    from zebra_agent_web.api import agent_engine
    from zebra_agent_web.api import engine as engine_module
    from zebra_agent_web.api.commons_import import WebCommonsServices

    workflow_library.owner_user_id = None
    workflow_engine.extras.update(
        {
            "__workflow_library__": workflow_library,
            "__commons__": WebCommonsServices(),
            "__metrics_store__": django_stores.metrics,
        }
    )

    async def _ready():
        return None

    monkeypatch.setattr(agent_engine, "ensure_initialized", _ready)
    monkeypatch.setattr(agent_engine, "get_library", lambda: workflow_library)
    monkeypatch.setattr(engine_module, "ensure_initialized", _ready)
    monkeypatch.setattr(engine_module, "get_engine", lambda: workflow_engine)
    monkeypatch.setattr(engine_module, "get_store", lambda: django_stores.store)
    return workflow_engine


@pytest.fixture
async def owner_client(async_client, test_user):
    from zebra_agent_web.api.models import SystemStateModel

    state, _ = await SystemStateModel.objects.aget_or_create(pk=1)
    state.commons_owner_user_id = test_user.id
    state.halted = False
    state.setup_completed = True
    await state.asave()
    await async_client.aforce_login(test_user)
    return async_client


async def _export_file(tmp_path, yaml_text: str) -> bytes:
    zebra_secret, device_secret = keys.generate_secret_key(), keys.generate_secret_key()
    cert = make_device_cert(
        zebra_secret, keys.public_key(device_secret), label="Pub", sphere="home", observed=False
    )
    root = tmp_path / f"publisher-{len(list(tmp_path.iterdir()))}"
    (root / "golden").mkdir(parents=True)
    (root / "golden" / "g.yaml").write_text(
        json.dumps({"id": "g", "workflow": "Capital Facts", **GOLDEN[0]})
    )
    pub = WorkflowLibrary(root / "lib", owner_user_id=1, golden_path=root / "golden")
    pub.add_workflow(yaml_text)
    text = await export_workflow(
        pub,
        "Capital Facts",
        device_secret=device_secret,
        zebra_pubkey=keys.public_key(zebra_secret),
        chain=[cert],
        display_name="Pub Zebra",
        with_golden=True,
    )
    return text.encode("utf-8")


async def _upload(client, data: bytes) -> str:
    response = await client.post(
        "/commons/workflow-import/",
        {"export_file": SimpleUploadedFile("wf.zebra.json", data, "application/json")},
    )
    assert response.status_code == 302, response.content
    assert response["Location"].startswith("/processes/"), response["Location"]
    return response["Location"].split("/")[2]


async def _settled(engine, process_id: str, timeout: float = 60.0):
    """Wait for the upload's background run to finish or park on a human task."""
    from zebra_agent_web.api import commons_import

    await asyncio.wait_for(asyncio.gather(*list(commons_import._background)), timeout)
    return await engine.store.load_process(process_id)


def _adopted(library) -> list[str]:
    return sorted(n for n, _ in library._read_named(library.library_path) if "(from " in n)


@pytest.mark.django_db(transaction=True)
async def test_owner_approves_import_then_runs_ask_first(
    tmp_path, web, workflow_library, owner_client, async_client
):
    engine = web
    process_id = await _upload(owner_client, await _export_file(tmp_path, _workflow()))
    process = await _settled(engine, process_id)
    assert process.state == ProcessState.RUNNING
    assert process.properties["golden_gym"]["import"]["decision"] == "passed"
    [approval] = await engine.get_pending_tasks(process_id)
    assert approval.task_definition_id == "owner_approval"
    assert _adopted(workflow_library) == []

    # Someone else cannot approve it
    from django.contrib.auth import get_user_model
    from django.test import AsyncClient

    other = await get_user_model().objects.acreate(username="not-the-owner")
    other_client = AsyncClient()
    await other_client.aforce_login(other)
    refused = await other_client.post(
        f"/api/tasks/{approval.id}/complete/",
        {"result": {"decision": "adopt"}},
        content_type="application/json",
    )
    assert refused.status_code == 403

    done = await owner_client.post(
        f"/api/tasks/{approval.id}/complete/",
        {"result": {"decision": "adopt"}},
        content_type="application/json",
    )
    assert done.status_code == 200, done.content
    process = await _settled(engine, process_id)
    assert process.properties["commons_import_result"]["status"] == "adopted"
    assert _adopted(workflow_library) == [LOCAL_NAME]
    assert workflow_library.is_supervised(LOCAL_NAME)

    # Its first goal run raises the pre-run approval before anything of it runs
    goal = await engine.create_process(
        load_definition_from_yaml(
            f"""name: Goal
first_task_id: execute
tasks:
  execute:
    name: Execute
    action: execute_goal_workflow
    properties: {{workflow_name: "{LOCAL_NAME}", goal: "capital of Australia"}}
"""
        )
    )
    await engine.start_process(goal.id)
    # ... and so does a scheduled routine
    start = datetime(2026, 11, 4, 3, 0, tzinfo=UTC)
    routines = RoutineRegistry()
    routines.register(Routine(name="nightly", schedule={"every": "1m"}, workflow=LOCAL_NAME))
    runs = InMemoryRoutineRunStore()
    await runs.upsert_run(RoutineRun("nightly", last_run=None, next_run=start - timedelta(1)))
    await SchedulerLoop(
        registry=routines, store=runs, engine=engine, clock=FakeClock(start)
    )._tick()

    entries = []
    for p in await engine.store.get_processes_by_state(ProcessState.RUNNING):
        launch = (p.properties or {}).get(SUPERVISED_LAUNCH_KEY)
        if launch:
            pending = await engine.get_pending_tasks(p.id)
            assert [t.task_definition_id for t in pending] == [APPROVAL_TASK]
            entries.append(launch["entry"])
    assert sorted(entries) == ["goal", "routine"]


@pytest.mark.django_db(transaction=True)
async def test_personal_data_file_is_rejected_and_nothing_saved(
    tmp_path, web, workflow_library, owner_client
):
    data = await _export_file(tmp_path, _workflow(prompt="Send it to jane.doe@gmail.com"))
    process = await _settled(web, await _upload(owner_client, data))
    result = process.properties["commons_import_result"]
    assert (result["status"], result["stage"]) == ("rejected", "pii")
    assert "personal data" in result["reason"]
    assert _adopted(workflow_library) == []


@pytest.mark.django_db(transaction=True)
async def test_file_delete_never_runs_in_the_gym_and_escalates(
    tmp_path, web, workflow_library, owner_client
):
    extra = """  tidy:
    name: "Tidy"
    action: file_delete
    properties: {path: "/tmp/never"}"""
    process_id = await _upload(owner_client, await _export_file(tmp_path, _workflow(extra=extra)))
    process = await _settled(web, process_id)
    gym = process.properties["golden_gym"]["import"]
    assert gym["decision"] == "escalate" and "file_delete" in gym["reason"]
    assert gym["golden_ids"] == []  # no gym run
    children = await web.store.list_child_processes(process_id)
    assert children == []
    [approval] = await web.get_pending_tasks(process_id)
    assert approval.task_definition_id == "owner_approval"
    assert _adopted(workflow_library) == []
