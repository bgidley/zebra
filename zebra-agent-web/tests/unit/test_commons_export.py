"""Signed export / import for this deployment (Commons S2b, #229).

Two deployments are simulated by switching the Commons key directory and the
workflow library between calls.
"""

from __future__ import annotations

import json

import pytest
from zebra_agent.commons.export import ExportRefused
from zebra_agent.commons.identity import make_device_revoke
from zebra_agent.library import LLM_DEFINED_TAG, WorkflowLibrary
from zebra_agent.provenance import read_commons
from zebra_agent_web.api import agent_engine, commons_export, commons_identity
from zebra_agent_web.api.commons_identity import CommonsError
from zebra_agent_web.api.models import CommonsDeviceModel, SystemStateModel

WORKFLOW = """name: "Project Update"
description: "Update a project plan"
tags: [planning]
version: 1
tasks:
  step1:
    name: "Step"
    action: llm_call
    properties:
      prompt: "Update the plan: {{goal}}"
"""


@pytest.fixture
def commons(settings, tmp_path):
    settings.ZEBRA_AGENT_SETTINGS = {
        **settings.ZEBRA_AGENT_SETTINGS,
        "COMMONS_ENABLED": True,
        "COMMONS_KEY_DIR": str(tmp_path / "keys"),
    }
    return settings


@pytest.fixture
def libraries(tmp_path, monkeypatch):
    home = WorkflowLibrary(tmp_path / "home", owner_user_id=1, sphere="home")
    work = WorkflowLibrary(tmp_path / "work", owner_user_id=1, sphere="work")
    current = {"lib": home}

    async def _ready():
        return None

    monkeypatch.setattr(agent_engine, "ensure_initialized", _ready)
    monkeypatch.setattr(agent_engine, "get_library", lambda: current["lib"])
    return home, work, current


async def _start():
    return await commons_identity.start_zebra(
        display_name="Home Zebra", label="Home server", sphere="home", observed=False
    )


@pytest.mark.django_db(transaction=True)
async def test_export_then_adopt_keeps_hash_and_adds_no_tag(commons, libraries):
    home, work, current = libraries
    await _start()
    home.add_workflow(WORKFLOW, llm_defined=True)
    sent = read_commons(home._files_named("Project Update")[0].read_text())

    text = await commons_export.export_workflow_file("Project Update")
    current["lib"] = work
    checked = await commons_export.import_workflow_file(text)
    assert checked["ok"] and checked["reason"] == "ok"
    assert checked["adopted"] is False
    assert checked["zebra_npub"].startswith("npub1")
    assert not list(work.library_path.glob("*.yaml"))

    result = await commons_export.import_workflow_file(
        text, adopt=True, expected_zebra=checked["zebra_npub"]
    )
    assert result["adopted"] and result["adopted_name"].startswith("Project Update (from ")
    saved = work._files_named(result["adopted_name"])[0].read_text()
    assert read_commons(saved)["content_sha256"] == sent["content_sha256"]
    assert read_commons(saved)["supervised"] is True
    assert LLM_DEFINED_TAG not in saved


@pytest.mark.django_db(transaction=True)
async def test_tampered_or_revoked_file_does_not_verify(commons, libraries):
    await _start()
    libraries[0].add_workflow(WORKFLOW)
    text = await commons_export.export_workflow_file("Project Update")

    tampered = text.replace("Update the plan", "Update the plam")
    result = await commons_export.import_workflow_file(tampered, adopt=True)
    assert result["ok"] is False and result["adopted"] is False

    data = json.loads(text)
    device = data["event"]["pubkey"]
    # As if the Zebra-key device revoked this one and the revoke reached this deployment.
    zebra_secret = await commons_identity.get_commons_keys().zebra_secret()
    row = await CommonsDeviceModel.objects.aget(device_pubkey=device)
    row.revoke_event = make_device_revoke(zebra_secret, device, reason="lost").to_dict()
    await row.asave()
    result = await commons_export.import_workflow_file(text)
    assert result == {**result, "ok": False, "reason": "revoked"}


@pytest.mark.django_db(transaction=True)
async def test_refusals(commons, libraries, settings):
    home = libraries[0]
    home.add_workflow(WORKFLOW)
    with pytest.raises(CommonsError, match="no Zebra identity"):
        await commons_export.export_workflow_file("Project Update")
    await _start()
    home.add_workflow(WORKFLOW.replace("[planning]", "[planning, system]"))
    with pytest.raises(ExportRefused, match="may not leave"):
        await commons_export.export_workflow_file("Project Update")
    with pytest.raises(CommonsError, match="invalid npub"):
        await commons_export.import_workflow_file("{}", expected_zebra="npub1bad")

    settings.ZEBRA_AGENT_SETTINGS = {**settings.ZEBRA_AGENT_SETTINGS, "COMMONS_ENABLED": False}
    with pytest.raises(CommonsError, match="off"):
        await commons_export.export_workflow_file("Project Update")
    with pytest.raises(CommonsError, match="off"):
        await commons_export.import_workflow_file("{}")


@pytest.mark.django_db(transaction=True)
def test_commands(commons, libraries, tmp_path, capsys):
    from django.core.management import call_command

    SystemStateModel.objects.filter(pk=1).delete()
    with pytest.raises(SystemExit):
        call_command("commons_export", "Project Update", "--out", str(tmp_path / "x.json"))

    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    with pytest.raises(SystemExit):
        call_command("commons_import", str(bad))
    assert '"ok": false' in capsys.readouterr().out
