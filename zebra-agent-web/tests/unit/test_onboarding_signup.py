"""The Oracle Cloud signup guide and pre-flight as the wizard's step 1 (#277, #312)."""

from __future__ import annotations

import json
import re

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from zebra_agent_web.api import onboarding as ob
from zebra_agent_web.api import onboarding_preflight as pf

OCID = "ocid1.tenancy.oc1..aaaaaaaabcdefghijklmnopqrstuvwxyz234567"
TICKS = {"account_created": "on", "budget_ack": "on"}


@pytest.mark.parametrize(
    "value,ok",
    [
        ("", True),
        (OCID, True),
        ("ocid1.tenancy.oc2..aaaaaaaabcdefghijklmnopqrstuvwxyz", True),
        ("ocid1.tenancy.oc1..short", False),
        ("ocid1.user.oc1..aaaaaaaabcdefghijklmnopqrstuvwxyz234567", False),
        ("tenancy", False),
        ("-----BEGIN RSA PRIVATE KEY-----", False),
        ("password: hunter2", False),
        ("sk-or-v1-abcdefghijklmnopqrstuvwx", False),
        ("aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99", False),
    ],
)
def test_ocid_shapes(value, ok):
    assert pf.validate_tenancy_ocid(value).ok is ok


@pytest.mark.parametrize(
    "value,ok,warns",
    [
        ("uk-london-1", True, 0),
        ("UK-London-1", True, 0),
        ("us-ashburn-1", True, 1),
        ("uk-cardiff-1", True, 1),
        ("london", False, 0),
        ("uk london 1", False, 0),
        ("", True, 0),
    ],
)
def test_region_shapes(value, ok, warns):
    result = pf.validate_region(value)
    assert result.ok is ok
    assert len(result.warnings) == warns


def test_cardiff_warning_says_no_26ai():
    assert "26ai" in pf.validate_region("uk-cardiff-1").warnings[0]


def test_check_signup_marks_a_requested_upgrade_pending():
    clean, errors = pf.check_signup({"payg": "none", "payg_requested": True, "home_region": ""})
    assert not errors
    assert clean["payg"] == "pending" and clean["home_region"] == pf.DEFAULT_REGION
    clean, _ = pf.check_signup({"payg": "active", "payg_requested": True})
    assert clean["payg"] == "active"
    clean, _ = pf.check_signup({"payg": "bogus"})
    assert clean["payg"] == "none"


def test_check_signup_drops_rejected_values():
    clean, errors = pf.check_signup({"tenancy_ocid": "-----BEGIN RSA PRIVATE KEY-----abc"})
    assert "tenancy_ocid" in errors
    assert clean["tenancy_ocid"] == ""
    assert "PRIVATE KEY" not in json.dumps(errors)


# ---------------------------------------------------------------------------
# In the wizard (needs the engine)
# ---------------------------------------------------------------------------

db = pytest.mark.django_db(transaction=True)


def _start() -> Client:
    client = Client()
    assert client.post("/onboarding/start/").status_code == 302
    return client


def _task_id(client: Client) -> str:
    html = client.get("/onboarding/").content.decode()
    return html.split('name="task_id" value="', 1)[1].split('"', 1)[0]


def _submit(client: Client, route: str = "done", **fields):
    return client.post(
        "/onboarding/step/", {"task_id": _task_id(client), "next_route": route, **fields}
    )


def _props() -> dict:
    from zebra_agent_web.api.models import ProcessInstanceModel

    [model] = ProcessInstanceModel.objects.all()
    return json.loads(model.properties)


@db
def test_step_one_is_the_guide_with_no_login_and_no_user(onboarding_env):
    users = get_user_model().objects.count()
    html = _start().get("/onboarding/").content.decode()
    assert 'data-testid="signup-guide"' in html
    assert "uk-london-1" in html
    assert "1-2 days" in html
    assert "cannot be changed later" in html
    assert "2 OCPUs and 12 GB" in html
    assert 'data-testid="guide-version"' in html and pf.ONBOARDING_GUIDE_VERSION in html
    assert html.index("1-2 days") < html.index('name="tenancy_ocid"')
    assert html.index("cannot be changed later") < html.index("signup-steps")
    assert get_user_model().objects.count() == users


@db
def test_external_links_open_safely(onboarding_env):
    html = _start().get("/onboarding/").content.decode()
    external = re.findall(r"<a [^>]*href=\"https://[^\"]+\"[^>]*>", html)
    assert len(external) >= 6
    assert all('target="_blank" rel="noopener"' in a for a in external)


@db
def test_answers_are_kept_in_process_properties_and_resume(onboarding_env):
    first = _start()
    response = _submit(
        first, tenancy_ocid=OCID, home_region="uk-london-1", payg_requested="on", **TICKS
    )
    assert response.status_code == 302
    stored = _props()["__task_output_signup"]
    assert stored["tenancy_ocid"] == OCID
    assert stored["payg"] == "pending"

    html = first.get("/onboarding/").content.decode()
    assert "Pay-As-You-Go: upgrade pending" in html and "Home region: uk-london-1" in html
    assert "Give access" in html

    token = first.cookies[ob.COOKIE_NAME].value
    second = Client()
    path = f"/onboarding/r/{token}/"
    assert second.get(path).status_code == 302
    assert "Pay-As-You-Go: upgrade pending" in second.get("/onboarding/").content.decode()

    other = _start()  # another visitor sees none of it
    other_html = other.get("/onboarding/").content.decode()
    assert OCID not in other_html and "Pay-As-You-Go: upgrade pending" not in other_html


@db
def test_the_next_step_stays_locked_until_the_ticks_are_set(onboarding_env):
    client = _start()
    response = _submit(client, home_region="uk-london-1", account_created="on")
    assert response.status_code == 400
    assert "Tick this to continue" in response.content.decode()
    assert "__task_output_signup" not in _props()
    assert "Give access" not in client.get("/onboarding/").content.decode().split("Steps")[0]
    assert "Step 1 of 6" in client.get("/onboarding/").content.decode()


@db
@pytest.mark.parametrize(
    "field,value",
    [
        ("tenancy_ocid", "-----BEGIN RSA PRIVATE KEY-----abc"),
        ("tenancy_ocid", "password: hunter2"),
        ("tenancy_ocid", "ocid1.user.oc1..aaaaaaaabcdefghijklmnopqrstuvwxyz234567"),
        ("home_region", "sk-or-v1-abcdefghijklmnopqrstuvwx"),
        ("home_region", "nowhere"),
        ("tenancy_ocid", "ocid1.tenancy.oc1..short"),
    ],
)
def test_bad_values_are_refused_never_stored_or_echoed(onboarding_env, field, value):
    client = _start()
    data = {"home_region": "uk-london-1", **TICKS, field: value}
    response = _submit(client, **data)
    assert response.status_code == 400
    html = response.content.decode()
    assert value not in html
    assert value not in json.dumps(_props())
    assert "__task_output_signup" not in _props()


@db
def test_a_secret_in_the_problem_text_is_not_echoed_back(onboarding_env):
    client = _start()
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----"
    response = _submit(client, "problem", problem=pem)
    assert response.status_code == 400
    assert "PRIVATE KEY" not in response.content.decode()


# ---------------------------------------------------------------------------
# The #277 URLs and the removed model
# ---------------------------------------------------------------------------


@db
@pytest.mark.parametrize("path", ["/onboarding/signup/", "/onboarding/signup/confirm/"])
def test_old_urls_redirect_to_the_wizard_without_login(onboarding_env, path):
    anonymous = Client(enforce_csrf_checks=True)
    for method in (anonymous.get, anonymous.post):
        response = method(path)
        assert response.status_code == 302
        assert response.url == "/onboarding/"


@db
@pytest.mark.parametrize("env_on, owner_on", [(False, True), (True, False), (False, False)])
@pytest.mark.parametrize("path", ["/onboarding/signup/", "/onboarding/signup/confirm/"])
def test_old_urls_are_404_while_off_for_get_and_post(
    onboarding_env, settings, env_on, owner_on, path
):
    from zebra_agent_web.api.models import SystemStateModel

    settings.ZEBRA_AGENT_SETTINGS = {**settings.ZEBRA_AGENT_SETTINGS, "ONBOARDING_ENABLED": env_on}
    SystemStateModel.objects.filter(pk=1).update(onboarding_enabled=owner_on)
    client = Client(enforce_csrf_checks=True)
    assert client.get(path).status_code == 404
    assert client.post(path).status_code == 404


def test_the_per_user_table_is_gone():
    from django.apps import apps

    assert not any(m.__name__ == "OnboardingSignupModel" for m in apps.get_models())
    from zebra_agent_web.api import models

    assert not hasattr(models, "OnboardingSignupModel")
