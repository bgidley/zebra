"""Oracle Cloud signup guide and pre-flight (#277)."""

from __future__ import annotations

import re

import pytest
from django.contrib.auth import get_user_model
from zebra_agent_web.api import onboarding_preflight as pf
from zebra_agent_web.api.models import OnboardingSignupModel

OCID = "ocid1.tenancy.oc1..aaaaaaaabcdefghijklmnopqrstuvwxyz234567"


@pytest.fixture(autouse=True)
def completed_setup(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
def on(settings):
    settings.ZEBRA_AGENT_SETTINGS = {**settings.ZEBRA_AGENT_SETTINGS, "ONBOARDING_ENABLED": True}


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


def test_off_returns_404(client, test_user):
    client.force_login(test_user)
    assert client.get("/onboarding/signup/").status_code == 404
    assert client.post("/onboarding/signup/confirm/", {}).status_code == 404


@pytest.mark.django_db
def test_guide_content(on, authenticated_client):
    html = authenticated_client.get("/onboarding/signup/").content.decode()
    assert "uk-london-1" in html
    assert "1-2 days" in html
    assert "Do not wait" in html or "do not wait" in html.lower()
    assert "cannot be changed later" in html
    assert "2 OCPUs and 12 GB" in html
    assert 'data-testid="guide-version"' in html
    assert html.index("1-2 days") < html.index("preflight-form")
    assert html.index("cannot be changed later") < html.index("signup-steps")


@pytest.mark.django_db
def test_external_links_open_safely(on, authenticated_client):
    html = authenticated_client.get("/onboarding/signup/").content.decode()
    external = re.findall(r"<a [^>]*href=\"https://[^\"]+\"[^>]*>", html)
    assert len(external) >= 6
    assert all('target="_blank"' in a and "noopener" in a for a in external)


@pytest.mark.django_db
def test_requires_login(on, client):
    response = client.get("/onboarding/signup/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_confirm_persists_and_resumes(on, authenticated_client, test_user):
    response = authenticated_client.post(
        "/onboarding/signup/confirm/",
        {
            "tenancy_ocid": OCID,
            "region": "uk-london-1",
            "payg": "pending",
            "account_created": "1",
            "budget_ack": "1",
        },
    )
    assert response.status_code == 200
    html = response.content.decode()
    assert "upgrade pending" in html
    assert 'data-testid="ready"' in html
    row = OnboardingSignupModel.objects.get(user_id=test_user.pk)
    assert row.data["tenancy_ocid"] == OCID
    assert row.data["payg"] == "pending"
    again = authenticated_client.get("/onboarding/signup/").content.decode()
    assert OCID in again
    assert "upgrade pending" in again


@pytest.mark.django_db
def test_not_ready_without_budget_ack(on, authenticated_client):
    html = authenticated_client.post(
        "/onboarding/signup/confirm/", {"region": "uk-london-1", "account_created": "1"}
    ).content.decode()
    assert 'data-testid="not-ready"' in html
    assert 'data-testid="ready"' not in html


@pytest.mark.django_db
def test_bad_values_rejected_not_stored_or_echoed(on, authenticated_client, test_user):
    secret = "-----BEGIN RSA PRIVATE KEY-----abc"
    response = authenticated_client.post(
        "/onboarding/signup/confirm/", {"tenancy_ocid": secret, "region": "nowhere"}
    )
    assert response.status_code == 422
    html = response.content.decode()
    assert "PRIVATE KEY" not in html
    assert "region id looks like" in html
    assert not OnboardingSignupModel.objects.filter(user_id=test_user.pk).exists()


@pytest.mark.django_db
def test_state_is_per_user(on, authenticated_client, client, test_user):
    authenticated_client.post(
        "/onboarding/signup/confirm/", {"tenancy_ocid": OCID, "region": "uk-london-1"}
    )
    other = get_user_model().objects.create_user("other", password="x")
    client.force_login(other)
    assert OCID not in client.get("/onboarding/signup/").content.decode()
