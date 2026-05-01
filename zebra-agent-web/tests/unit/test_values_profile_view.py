"""Integration tests for the /profile/values/ wizard entry-point view.

Uses an in-memory engine and an InMemoryProfileStore (no Oracle). The wizard
workflow YAML is loaded from disk so the test exercises the real definition.
The LLM-driven extract step is stubbed at the action level so no network
calls are made.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_agent.profile import ValuesProfileVersion
from zebra_agent.storage.profile import InMemoryProfileStore
from zebra_tasks.agent.load_values_profile import LoadValuesProfileAction
from zebra_tasks.agent.save_values_profile import SaveValuesProfileAction

pytestmark = [pytest.mark.django_db(transaction=True)]


WIZARD_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "zebra-agent"
    / "workflows"
    / "values_profile_wizard.yaml"
)


@pytest.fixture(autouse=True)
def _ensure_setup_complete(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


class _StubExtract(TaskAction):
    async def run(self, task, context):
        return TaskResult.ok(output={"extracted_tags": {}, "model": "stub"})


@pytest.fixture
def profile_store() -> InMemoryProfileStore:
    return InMemoryProfileStore()


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def wf_engine(store, profile_store) -> WorkflowEngine:
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("load_values_profile", LoadValuesProfileAction)
    registry.register_action("extract_values_tags", _StubExtract)
    registry.register_action("save_values_profile", SaveValuesProfileAction)
    return WorkflowEngine(store, registry, extras={"__profile_store__": profile_store})


@pytest.fixture
def wizard_definition():
    with open(WIZARD_PATH) as f:
        return load_definition_from_yaml(f.read())


class _StubLibrary:
    def __init__(self, definition):
        self._definition = definition

    def get_workflow(self, name):
        if name != "Values Profile Wizard":
            raise ValueError(f"Unknown workflow: {name}")
        return self._definition

    async def list_workflows(self):
        return []


@pytest.fixture(autouse=True)
def patch_singletons(store, wf_engine, profile_store, wizard_definition):
    """Patch the global engine and agent_engine singletons used by the view."""
    import zebra_agent_web.api.agent_engine as agent_engine_module
    import zebra_agent_web.api.engine as engine_module

    old_store = engine_module._store
    old_engine = engine_module._engine
    engine_module._store = store
    engine_module._engine = wf_engine

    old_library = agent_engine_module._library
    old_profile = agent_engine_module._profile
    agent_engine_module._library = _StubLibrary(wizard_definition)
    agent_engine_module._profile = profile_store

    yield

    engine_module._store = old_store
    engine_module._engine = old_engine
    agent_engine_module._library = old_library
    agent_engine_module._profile = old_profile


@pytest.fixture
def authenticated_client(db):
    from django.contrib.auth import get_user_model
    from django.test import AsyncClient

    User = get_user_model()
    user = User.objects.create_user(username="testuser")
    c = AsyncClient()
    c.force_login(user)
    return c, user


@pytest.fixture
def anonymous_client():
    from django.test import AsyncClient

    return AsyncClient()


async def test_anonymous_user_is_redirected(anonymous_client):
    response = await anonymous_client.get("/profile/values/")
    # The view falls through to setup redirect for unauthenticated users.
    # Test settings strip LoginRequiredMiddleware, so we hit our explicit check.
    assert response.status_code == 302
    assert "/setup" in response.url or "/login" in response.url


async def test_user_with_no_profile_lands_on_first_form(authenticated_client):
    client, user = authenticated_client

    response = await client.get("/profile/values/")

    assert response.status_code == 302
    # Redirected to the human-task page for the first pending task.
    assert response.url.startswith("/tasks/")


async def test_user_with_existing_profile_lands_in_edit_mode(
    authenticated_client, profile_store, wf_engine
):
    client, user = authenticated_client

    saved = await profile_store.save_version(
        user_id=user.id,
        version=ValuesProfileVersion(core_values_text="prior text"),
    )

    response = await client.get("/profile/values/")
    assert response.status_code == 302

    # Find the just-created process and confirm it carries existing_profile_version_id.
    processes = list(wf_engine.store._processes.values())
    assert len(processes) == 1
    process = processes[0]
    assert process.properties.get("existing_profile_version_id") == saved.id
    assert process.properties.get("user_id") == user.id

    # And the load_values_profile action wrote the existing profile into properties.
    existing = process.properties.get("existing_profile")
    assert existing is not None
    assert existing["core_values_text"] == "prior text"
    assert existing["mode"] == "edit"
