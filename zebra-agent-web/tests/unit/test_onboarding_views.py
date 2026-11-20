"""The /onboarding/ wizard pages (#276): switch, resume, steps, failures, limits."""

from __future__ import annotations

import json

import pytest
from django.test import Client
from zebra_agent_web.api import onboarding as ob

pytestmark = pytest.mark.django_db(transaction=True)


def _prod_middleware() -> list[str]:
    """settings.MIDDLEWARE as declared in settings.py (test settings drop login + setup)."""
    import ast
    from pathlib import Path

    import zebra_agent_web.settings as prod_settings

    tree = ast.parse(Path(prod_settings.__file__).read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "MIDDLEWARE" for t in node.targets
        ):
            return list(ast.literal_eval(node.value))
    raise AssertionError("MIDDLEWARE not found in settings.py")


def _process_props():
    from zebra_agent_web.api.models import ProcessInstanceModel

    [model] = ProcessInstanceModel.objects.all()
    return model, json.loads(model.properties)


def _start(client: Client):
    response = client.post("/onboarding/start/")
    assert response.status_code == 302, response.content
    return response


def _current_task_id(client: Client) -> str:
    html = client.get("/onboarding/").content.decode()
    marker = 'name="task_id" value="'
    return html.split(marker, 1)[1].split('"', 1)[0]


def _submit(client: Client, route: str | None, **fields):
    data = {"task_id": _current_task_id(client), **fields}
    if route:
        data["next_route"] = route
    return client.post("/onboarding/step/", data)


# ---------------------------------------------------------------------------
# O4: off means 404 and nothing is created
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("env_on, owner_on", [(False, True), (True, False), (False, False)])
def test_off_means_404_everywhere(onboarding_env, settings, env_on, owner_on):
    from django.contrib.auth import get_user_model
    from zebra_agent_web.api.models import ProcessInstanceModel, SystemStateModel

    settings.ZEBRA_AGENT_SETTINGS = {**settings.ZEBRA_AGENT_SETTINGS, "ONBOARDING_ENABLED": env_on}
    SystemStateModel.objects.filter(pk=1).update(onboarding_enabled=owner_on)
    users = get_user_model().objects.count()
    client = Client()
    for method, path in [
        ("get", "/onboarding/"),
        ("post", "/onboarding/start/"),
        ("post", "/onboarding/step/"),
        ("get", f"/onboarding/r/{ob.make_token('p', 'n')}/"),
        ("post", "/onboarding/new-link/"),
        ("post", "/onboarding/forget/"),
    ]:
        assert getattr(client, method)(path).status_code == 404, path
    assert not ProcessInstanceModel.objects.exists()
    assert get_user_model().objects.count() == users


def test_on_the_wizard_is_reachable_without_signing_in(onboarding_env, settings):
    settings.MIDDLEWARE = _prod_middleware()
    response = Client().get("/onboarding/")
    assert response.status_code == 200
    assert "Get your own Zebra" in response.content.decode()


def test_starting_creates_a_session_but_no_user(onboarding_env, settings):
    from django.contrib.auth import get_user_model

    settings.MIDDLEWARE = _prod_middleware()
    users = get_user_model().objects.count()
    client = Client()
    response = _start(client)

    cookie = response.cookies[ob.COOKIE_NAME]
    assert cookie["httponly"] and cookie["samesite"] == "Lax"
    model, props = _process_props()
    assert model.state == "running" and model.user_id is None
    assert get_user_model().objects.count() == users


def test_the_manage_page_is_behind_login_and_owner_only(onboarding_env, settings, test_user):
    from django.contrib.auth import get_user_model
    from zebra_agent_web.api.models import SystemStateModel

    settings.MIDDLEWARE = _prod_middleware()
    assert Client().get("/onboarding/manage/").status_code == 302

    owner = Client()
    owner.force_login(test_user)  # the first user is the owner
    assert owner.get("/onboarding/manage/").status_code == 200
    owner.post("/onboarding/manage/", {"enabled": "0"})
    assert SystemStateModel.objects.get(pk=1).onboarding_enabled is False
    assert Client().get("/onboarding/").status_code == 404

    other = Client()
    other.force_login(get_user_model().objects.create_user(username="other"))
    assert other.post("/onboarding/manage/", {"enabled": "1"}).status_code == 403
    assert SystemStateModel.objects.get(pk=1).onboarding_enabled is False


# ---------------------------------------------------------------------------
# O1: closing the browser resumes at the same step; O2: no secret stored
# ---------------------------------------------------------------------------


def test_resume_link_brings_a_new_browser_back_to_the_same_step(onboarding_env):
    first = Client()
    _start(first)
    assert _submit(first, "done", home_region="uk-london-1").status_code == 302
    html = first.get("/onboarding/").content.decode()
    assert "Give access" in html
    resume = html.split('aria-label="Resume link"', 1)[0].rsplit('value="', 1)[1].split('"')[0]
    path = resume.split("testserver", 1)[1]

    second = Client()  # a closed browser: no cookie
    assert "Start" in second.get("/onboarding/").content.decode()
    response = second.get(path)
    assert response.status_code == 302 and ob.COOKIE_NAME in response.cookies
    html = second.get("/onboarding/").content.decode()
    assert 'aria-current="step"' in html
    assert html.split('aria-current="step"', 1)[1].split("</li>", 1)[0].count("Give access") == 1


def test_no_secret_in_properties(onboarding_env):
    client = Client()
    _start(client)
    token = client.cookies[ob.COOKIE_NAME].value
    _submit(client, "done", home_region="uk-london-1")
    _model, props = _process_props()
    _pid, nonce = ob.read_token(token)
    text = json.dumps(props)
    assert nonce not in text and token not in text
    assert props[ob.NONCE_KEY] == ob.nonce_hash(nonce)


def test_private_keys_are_refused_and_never_stored(onboarding_env):
    client = Client()
    _start(client)
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----"
    response = _submit(client, "problem", problem=pem)
    assert response.status_code == 400
    assert "Never paste keys here" in response.content.decode()
    _model, props = _process_props()
    assert "PRIVATE KEY" not in json.dumps(props)
    assert "__task_output_signup" not in props


def test_new_link_invalidates_the_old_cookie(onboarding_env):
    client = Client()
    _start(client)
    old = client.cookies[ob.COOKIE_NAME].value
    client.post("/onboarding/new-link/")
    stale = Client()
    stale.cookies[ob.COOKIE_NAME] = old
    assert 'name="task_id"' not in stale.get("/onboarding/").content.decode()
    assert 'name="task_id"' in client.get("/onboarding/").content.decode()
    assert stale.get(f"/onboarding/r/{old}/").status_code == 410


def test_forget_me_ends_the_session(onboarding_env):
    client = Client()
    _start(client)
    old = client.cookies[ob.COOKIE_NAME].value
    client.post("/onboarding/forget/")
    model, _ = _process_props()
    assert model.state == "failed"
    assert Client().get(f"/onboarding/r/{old}/").status_code == 410


# ---------------------------------------------------------------------------
# O3: a failure shows the reason and a retry; later steps stay locked
# ---------------------------------------------------------------------------


def test_a_failed_step_shows_its_reason_and_a_retry_and_locks_later_steps(onboarding_env):
    client = Client()
    _start(client)
    assert _submit(client, "problem", problem="Oracle rejected my card").status_code == 302

    html = client.get("/onboarding/").content.decode()
    assert "did not finish" in html
    assert "Oracle rejected my card" in html
    assert "Try this step again" in html
    assert html.count('aria-label="locked"') == 5

    # Later steps cannot be completed: only the current task id is accepted
    response = client.post("/onboarding/step/", {"task_id": "someone-else", "next_route": "done"})
    assert response.status_code == 409

    assert _submit(client, None).status_code == 302  # retry
    html = client.get("/onboarding/").content.decode()
    assert "Step 1 of 6" in html and "Your Oracle Cloud account" in html


def test_problem_needs_a_reason(onboarding_env):
    client = Client()
    _start(client)
    response = _submit(client, "problem", problem="  ")
    assert response.status_code == 400
    assert "Tell us what went wrong" in response.content.decode()


def test_a_required_confirmation_must_be_ticked(onboarding_env):
    client = Client()
    _start(client)
    _submit(client, "done", home_region="uk-london-1")
    response = _submit(client, "done")
    assert response.status_code == 400
    assert "Tick this to continue" in response.content.decode()


def test_unknown_route_is_refused(onboarding_env):
    client = Client()
    _start(client)
    assert _submit(client, "skip_ahead", home_region="uk-london-1").status_code == 400


def test_the_whole_wizard_finishes(onboarding_env):
    client = Client()
    _start(client)
    _submit(client, "done", home_region="uk-london-1")
    _submit(client, "done", ready="on")
    _submit(client, "done", applied="on")
    _submit(client, "done", working="on")
    _submit(client, "done")
    _submit(client, "done")
    assert "All done" in client.get("/onboarding/").content.decode()
    model, _ = _process_props()
    assert model.state == "complete"


def test_htmx_submit_returns_the_step_partial(onboarding_env):
    client = Client()
    _start(client)
    data = {"task_id": _current_task_id(client), "next_route": "done", "home_region": "uk-london-1"}
    response = client.post("/onboarding/step/", data, HTTP_HX_REQUEST="true")
    html = response.content.decode()
    assert response.status_code == 200
    assert html.lstrip().startswith('<div id="onboarding-step"')
    assert "Give access" in html


# ---------------------------------------------------------------------------
# Guardrails (S2): rate limits, kill switch
# ---------------------------------------------------------------------------


def test_the_sixth_session_from_one_ip_in_an_hour_gets_429(onboarding_env):
    for _ in range(5):
        _start(Client())
    response = Client().post("/onboarding/start/")
    assert response.status_code == 429
    other_ip = Client(REMOTE_ADDR="203.0.113.9")
    assert other_ip.post("/onboarding/start/").status_code == 302


def test_proxy_header_is_used_only_when_configured(onboarding_env, settings):
    settings.ZEBRA_AGENT_SETTINGS = {
        **settings.ZEBRA_AGENT_SETTINGS,
        "ONBOARDING_CLIENT_IP_HEADER": "CF-Connecting-IP",
        "ONBOARDING_SESSIONS_PER_IP_HOUR": 1,
    }
    assert (
        Client(HTTP_CF_CONNECTING_IP="198.51.100.1").post("/onboarding/start/").status_code == 302
    )
    assert (
        Client(HTTP_CF_CONNECTING_IP="198.51.100.1").post("/onboarding/start/").status_code == 429
    )
    assert (
        Client(HTTP_CF_CONNECTING_IP="198.51.100.2").post("/onboarding/start/").status_code == 302
    )


def test_requests_per_minute_limit(onboarding_env, settings):
    settings.ZEBRA_AGENT_SETTINGS = {
        **settings.ZEBRA_AGENT_SETTINGS,
        "ONBOARDING_REQUESTS_PER_IP_MINUTE": 3,
    }
    client = Client()
    assert [client.get("/onboarding/").status_code for _ in range(4)] == [200, 200, 200, 429]


def test_kill_switch_pauses_the_wizard(onboarding_env):
    from zebra_agent_web.api.kill_switch import set_halted_sync

    client = Client()
    _start(client)
    task_id = _current_task_id(client)
    set_halted_sync(True, "test")
    assert "paused" in client.get("/onboarding/").content.decode()
    response = client.post(
        "/onboarding/step/",
        {"task_id": task_id, "next_route": "done", "home_region": "uk-london-1"},
    )
    assert response.status_code == 503
    assert Client(REMOTE_ADDR="203.0.113.7").post("/onboarding/start/").status_code == 503
