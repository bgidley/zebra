"""E2E: the anonymous onboarding wizard on real settings and the real store (#276).

Production middleware (login required, setup redirects) is active: the wizard must work
for a visitor with no account. O1: closing the browser and returning with the resume link
lands on the same step. O3: a failed step shows its reason and a retry, later steps locked.
"""

from __future__ import annotations

import pytest
from django.test import AsyncClient

pytestmark = pytest.mark.e2e


async def _noop() -> None:
    return None


@pytest.fixture
def onboarding_on(settings, monkeypatch, workflow_engine, workflow_library):
    import zebra_agent_web.api.agent_engine as agent_engine_module
    import zebra_agent_web.api.engine as engine_module
    from django.core.cache import cache
    from zebra_agent_web.api.models import SystemStateModel

    monkeypatch.setattr(engine_module, "_store", workflow_engine.store)
    monkeypatch.setattr(engine_module, "_engine", workflow_engine)
    monkeypatch.setattr(agent_engine_module, "_library", workflow_library)
    monkeypatch.setattr(agent_engine_module, "ensure_initialized", _noop)
    monkeypatch.setattr(engine_module, "ensure_initialized", _noop)
    settings.ZEBRA_AGENT_SETTINGS = {**settings.ZEBRA_AGENT_SETTINGS, "ONBOARDING_ENABLED": True}
    SystemStateModel.objects.update_or_create(
        pk=1, defaults={"onboarding_enabled": True, "setup_completed": True}
    )
    cache.clear()
    yield workflow_engine
    cache.clear()


async def _task_id(client: AsyncClient) -> str:
    html = (await client.get("/onboarding/")).content.decode()
    return html.split('name="task_id" value="', 1)[1].split('"', 1)[0]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_resume_lands_on_the_same_step_after_a_failure_and_retry(onboarding_on):
    from zebra_agent_web.api import onboarding as ob

    browser = AsyncClient()
    assert (await browser.get("/onboarding/")).status_code == 200
    assert (await browser.post("/onboarding/start/")).status_code == 302

    # Step 1 done
    response = await browser.post(
        "/onboarding/step/",
        {"task_id": await _task_id(browser), "next_route": "done", "home_region": "uk-london-1"},
    )
    assert response.status_code == 302

    # Step 2 fails with a reason: retry screen, later steps locked (O3)
    response = await browser.post(
        "/onboarding/step/",
        {"task_id": await _task_id(browser), "next_route": "problem", "problem": "Not an admin"},
    )
    assert response.status_code == 302
    html = (await browser.get("/onboarding/")).content.decode()
    assert "did not finish" in html and "Not an admin" in html
    assert html.count('aria-label="locked"') == 4

    # Close the browser; come back on another one with the resume link (O1)
    resume = html.split('aria-label="Resume link"', 1)[0].rsplit('value="', 1)[1].split('"')[0]
    returning = AsyncClient()
    response = await returning.get(resume.split("testserver", 1)[1])
    assert response.status_code == 302
    html = (await returning.get("/onboarding/")).content.decode()
    assert "did not finish" in html and "Not an admin" in html

    # Retry, then the step itself again
    response = await returning.post("/onboarding/step/", {"task_id": await _task_id(returning)})
    assert response.status_code == 302
    html = (await returning.get("/onboarding/")).content.decode()
    assert "Step 2 of 6" in html

    # Nothing secret is stored on the process
    store = onboarding_on.store
    [token] = [c.value for c in returning.cookies.values() if c.key == ob.COOKIE_NAME]
    process = await ob.load_session(store, token)
    text = str(process.properties)
    assert ob.read_token(token)[1] not in text and token not in text
