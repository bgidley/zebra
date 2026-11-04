"""Web side of the judged import and supervised use (Commons S3, #230)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from zebra_agent.library import WorkflowLibrary
from zebra_agent.provenance import read_commons, relabel
from zebra_agent_web.api import agent_engine
from zebra_agent_web.api.commons_identity import CommonsError
from zebra_agent_web.api.commons_import import (
    WebCommonsServices,
    owner_only_refusal,
    start_judged_import,
)
from zebra_agent_web.api.models import SystemStateModel

WORKFLOW = """name: "Shared"
description: "x"
tasks:
  a: {name: A, action: llm_call, properties: {prompt: hi}}
"""


@pytest.fixture
def commons_on(settings):
    settings.ZEBRA_AGENT_SETTINGS = {**settings.ZEBRA_AGENT_SETTINGS, "COMMONS_ENABLED": True}
    return settings


@pytest.fixture
def library(tmp_path, monkeypatch) -> WorkflowLibrary:
    publisher = WorkflowLibrary(tmp_path / "pub", owner_user_id=1)
    publisher.add_workflow(WORKFLOW)
    text = next(publisher.library_path.glob("*.yaml")).read_text()
    block = read_commons(text)
    lib = WorkflowLibrary(tmp_path / "lib", owner_user_id=1)
    lib.save(
        relabel(text),
        writer="adopt",
        received=block,
        expected_sha256=block["content_sha256"],
        name="Shared (from Pub)",
    )

    async def _ready():
        return None

    monkeypatch.setattr(agent_engine, "ensure_initialized", _ready)
    monkeypatch.setattr(agent_engine, "get_library", lambda: lib)
    return lib


@pytest.mark.django_db(transaction=True)
async def test_stop_reason_follows_switch_and_kill_switch(settings, commons_on):
    services = WebCommonsServices()
    await SystemStateModel.objects.aupdate_or_create(pk=1, defaults={"halted": False})
    assert await services.stop_reason() is None
    await SystemStateModel.objects.filter(pk=1).aupdate(halted=True)
    assert await services.stop_reason() == "the kill switch is on"
    settings.ZEBRA_AGENT_SETTINGS = {**settings.ZEBRA_AGENT_SETTINGS, "COMMONS_ENABLED": False}
    assert "off" in await services.stop_reason()
    assert await services.held_events() == []


@pytest.mark.django_db(transaction=True)
async def test_start_judged_import_refused_while_stopped(commons_on):
    await SystemStateModel.objects.aupdate_or_create(pk=1, defaults={"halted": True})
    with pytest.raises(CommonsError, match="kill switch"):
        await start_judged_import("{}", user_id=None)


@pytest.mark.django_db(transaction=True)
async def test_owner_only_tasks_refuse_other_users(test_user):
    await SystemStateModel.objects.aupdate_or_create(
        pk=1, defaults={"commons_owner_user_id": test_user.id, "setup_completed": True}
    )
    other = await get_user_model().objects.acreate(username="someone-else")
    task_def = SimpleNamespace(properties={"owner_only": True})
    assert await owner_only_refusal(test_user, task_def) is None
    assert "owner" in await owner_only_refusal(other, task_def)
    assert await owner_only_refusal(other, SimpleNamespace(properties={})) is None


@pytest.mark.django_db(transaction=True)
async def test_pause_all_resupervises_adopted_workflows(
    authenticated_async_client, library, monkeypatch
):
    from zebra_agent.storage.trust import InMemoryTrustStore

    monkeypatch.setattr(agent_engine, "get_trust", lambda: InMemoryTrustStore())
    library.clear_supervision("Shared (from Pub)")
    response = await authenticated_async_client.post(
        "/api/trust/pause-all/", {"reason": "test"}, content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["resupervised"] == ["Shared (from Pub)"]
    assert library.is_supervised("Shared (from Pub)")


@pytest.mark.django_db(transaction=True)
async def test_owner_clears_supervision(authenticated_async_client, test_user, library, commons_on):
    await SystemStateModel.objects.aupdate_or_create(
        pk=1, defaults={"commons_owner_user_id": test_user.id, "setup_completed": True}
    )
    response = await authenticated_async_client.post(
        "/commons/workflows/Shared%20(from%20Pub)/clear-supervision/"
    )
    assert response.status_code == 302
    assert not library.is_supervised("Shared (from Pub)")


@pytest.mark.django_db(transaction=True)
async def test_non_owner_cannot_upload(async_client, test_user, commons_on):
    await SystemStateModel.objects.aupdate_or_create(
        pk=1, defaults={"commons_owner_user_id": test_user.id, "setup_completed": True}
    )
    other = await get_user_model().objects.acreate(username="someone-else")
    await async_client.aforce_login(other)
    response = await async_client.post("/commons/workflow-import/")
    assert response.status_code == 403
