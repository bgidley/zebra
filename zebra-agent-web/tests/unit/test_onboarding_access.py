"""The onboarding access step (#278 S3): deploy link, policy text, revoke screen."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest
from django.test import Client
from zebra_agent_web.api import onboarding_access as access

pytestmark = pytest.mark.django_db(transaction=True)

DESIGN = Path(__file__).resolve().parents[3] / "specs" / "onboarding-design.md"


def _current_task_id(client: Client) -> str:
    page = client.get("/onboarding/").content.decode()
    return page.split('name="task_id" value="', 1)[1].split('"', 1)[0]


def _submit(client: Client, route: str | None, **fields):
    data = {"task_id": _current_task_id(client), **fields}
    if route:
        data["next_route"] = route
    return client.post("/onboarding/step/", data)


def _to_access(client: Client) -> None:
    assert client.post("/onboarding/start/").status_code == 302
    assert _submit(client, "done", home_region="uk-london-1").status_code == 302


def _props():
    from zebra_agent_web.api.models import ProcessInstanceModel

    [model] = ProcessInstanceModel.objects.all()
    return model, json.loads(model.properties)


# ---------------------------------------------------------------------------
# The policy text is the design's, scoped to one compartment
# ---------------------------------------------------------------------------


def _design_policy_blocks() -> list[str]:
    section = DESIGN.read_text().split("### Policy text", 1)[1].split("\n## ", 1)[0]
    return [b.strip("\n") for b in re.findall(r"```\n(.*?)```", section, flags=re.S)]


def test_policy_text_is_the_design_text():
    assert _design_policy_blocks() == [
        access.COMPARTMENT_POLICY,
        access.TENANCY_POLICY,
        access.RUNTIME_POLICY,
    ]


def test_compartment_policy_names_one_compartment_and_tenancy_grants_are_separate():
    policy = access.policy_text("mine")
    lines = policy.compartment.splitlines()
    assert len(lines) == 8
    assert all(line.endswith("in compartment zebra-mine") for line in lines)
    assert "tenancy" not in policy.compartment and "all-resources" not in policy.compartment
    assert policy.tenancy.splitlines() == [
        "Allow group zebra-mine-admins to manage usage-budgets in tenancy",
        "Allow group zebra-mine-admins to manage quota in tenancy",
    ]
    assert "in tenancy" not in policy.runtime


@pytest.mark.parametrize("bad", ["", "Mine", "9lives", "a" * 21, "x y", "<script>", None, 3])
def test_a_bad_name_falls_back_to_the_placeholder(bad):
    assert access.policy_text(bad).compartment == access.COMPARTMENT_POLICY


# ---------------------------------------------------------------------------
# The Deploy to Oracle Cloud link only with an https stack zip URL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url", ["", "   ", "http://example.com/zebra.zip", "ftp://x/y.zip", "https://u:p@x/y.zip"]
)
def test_no_deploy_link_without_an_https_stack_url(settings, url):
    settings.ZEBRA_AGENT_SETTINGS = {
        **settings.ZEBRA_AGENT_SETTINGS,
        "ONBOARDING_STACK_ZIP_URL": url,
    }
    assert not access.stack().available


def test_deploy_link_points_resource_manager_at_the_zip(settings):
    zip_url = "https://releases.example.com/zebra-stack-1.2.0.zip"
    settings.ZEBRA_AGENT_SETTINGS = {
        **settings.ZEBRA_AGENT_SETTINGS,
        "ONBOARDING_STACK_ZIP_URL": zip_url,
        "ONBOARDING_STACK_ZIP_SHA256": "A" * 64,
    }
    stack = access.stack()
    assert stack.deploy_url == (
        "https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl="
        "https%3A%2F%2Freleases.example.com%2Fzebra-stack-1.2.0.zip"
    )
    assert stack.sha256 == "a" * 64


def test_access_step_hides_the_link_while_no_stack_is_published(onboarding_env):
    client = Client()
    _to_access(client)
    page = client.get("/onboarding/").content.decode()
    assert "must be a tenancy administrator" in page
    assert "create_guardrails = false" in page
    assert "not available on this server yet" in page
    assert "cloud.oracle.com/resourcemanager" not in page


def test_access_step_shows_the_link_when_a_stack_is_published(onboarding_env, settings):
    settings.ZEBRA_AGENT_SETTINGS = {
        **settings.ZEBRA_AGENT_SETTINGS,
        "ONBOARDING_STACK_ZIP_URL": "https://releases.example.com/stack.zip",
    }
    client = Client()
    _to_access(client)
    page = client.get("/onboarding/").content.decode()
    assert 'href="https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=' in page
    assert 'rel="noopener noreferrer"' in page


# ---------------------------------------------------------------------------
# The fallback shows the policy, takes no key
# ---------------------------------------------------------------------------


def test_policy_fallback_shows_the_policy_for_the_chosen_name(onboarding_env):
    client = Client()
    _to_access(client)
    assert _submit(client, "policy", name="home").status_code == 302
    page = client.get("/onboarding/").content.decode()
    blocks = dict(re.findall(r'data-policy="(\w+)">(.*?)</pre>', page, flags=re.S))
    expected = access.policy_text("home")
    assert html.unescape(blocks["compartment"]) == expected.compartment
    assert html.unescape(blocks["tenancy"]) == expected.tenancy
    assert html.unescape(blocks["runtime"]) == expected.runtime
    assert "must be a tenancy administrator" in page
    # Back to the stack choice, or on to provisioning
    assert _submit(client, "back").status_code == 302
    assert "Choose how your Zebra gets built" in client.get("/onboarding/").content.decode()


def test_a_bad_name_is_refused(onboarding_env):
    client = Client()
    _to_access(client)
    response = _submit(client, "policy", name="Bad Name!")
    assert response.status_code == 400


def test_the_access_step_has_no_field_for_a_key_or_secret():
    from zebra.definitions.loader import load_definition
    from zebra_agent.library import BUILTIN_WORKFLOWS_DIR

    definition = load_definition(BUILTIN_WORKFLOWS_DIR / "onboarding.yaml")
    fields = set()
    for task_id in ("access", "access_policy", "provision"):
        schema = definition.tasks[task_id].properties["schema"]
        fields |= set(schema.get("properties", {}))
    assert fields <= {"name", "problem", "applied"}
    assert not re.search(r"key|secret|password|fingerprint|ocid", " ".join(fields))


# ---------------------------------------------------------------------------
# Revoke: reachable from every terminal state and without a session
# ---------------------------------------------------------------------------


def test_revoke_is_reachable_without_a_session(onboarding_env):
    client = Client()
    assert 'href="/onboarding/revoke/"' in client.get("/onboarding/").content.decode()
    page = client.get("/onboarding/revoke/").content.decode()
    assert "How to undo everything" in page
    assert "Destroy the stack" in page and "zebra-&lt;name&gt;" in page


def test_revoke_fills_in_the_sessions_name(onboarding_env):
    client = Client()
    _to_access(client)
    _submit(client, "done", name="home")
    page = client.get("/onboarding/revoke/").content.decode()
    assert "zebra-home-admins" in page


def test_revoke_is_linked_from_the_ended_state(onboarding_env):
    from zebra_agent_web.api.models import ProcessInstanceModel

    client = Client()
    _to_access(client)
    # Expiry or any failure ends the session: it shows "ended" with the revoke link
    model, _ = _props()
    ProcessInstanceModel.objects.filter(id=model.id).update(state="failed")
    page = client.get("/onboarding/").content.decode()
    assert "This session has ended" in page
    assert 'href="/onboarding/revoke/"' in page
    # "Forget me" drops the session; the start screen still links to revoke
    client.post("/onboarding/forget/")
    assert 'href="/onboarding/revoke/"' in client.get("/onboarding/").content.decode()


def test_revoke_is_linked_from_every_step(onboarding_env):
    client = Client()
    _to_access(client)
    assert 'href="/onboarding/revoke/"' in client.get("/onboarding/").content.decode()
