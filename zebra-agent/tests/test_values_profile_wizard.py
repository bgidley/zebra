"""End-to-end test for the values_profile_wizard.yaml system workflow.

Drives the wizard with the real load_values_profile and save_values_profile
actions plus an InMemoryProfileStore. The LLM-driven extract step is stubbed
(no network calls).

Covers both capture mode (no existing profile) and edit mode (existing
profile pre-populates the form defaults).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.agent.load_values_profile import LoadValuesProfileAction
from zebra_tasks.agent.save_values_profile import SaveValuesProfileAction

from zebra_agent.profile import ValuesProfileVersion
from zebra_agent.storage.profile import InMemoryProfileStore

WIZARD_PATH = Path(__file__).parent.parent / "workflows" / "values_profile_wizard.yaml"


class StubExtractTags(TaskAction):
    """Stub the LLM-backed extract step with a fixed extraction."""

    async def run(self, task, context):
        extracted = {
            "core_values": {
                "approved_tags": [],
                "candidate_tags": [{"slug": "honesty", "label": "Honesty"}],
            },
            "ethical_positions": {"approved_tags": [], "candidate_tags": []},
            "priorities": {"approved_tags": [], "candidate_tags": []},
            "deal_breakers": {
                "approved_tags": [],
                "candidate_tags": [{"slug": "no-deception", "label": "No deception"}],
            },
        }
        key = task.properties.get("output_key", "extracted_tags")
        context.set_process_property(key, extracted)
        return TaskResult.ok(output={"extracted_tags": extracted, "model": "stub-model"})


@pytest.fixture
def definition():
    with open(WIZARD_PATH) as f:
        return load_definition_from_yaml(f.read())


@pytest.fixture
def registry():
    reg = ActionRegistry()
    reg.register_defaults()
    reg.register_action("load_values_profile", LoadValuesProfileAction)
    reg.register_action("extract_values_tags", StubExtractTags)
    reg.register_action("save_values_profile", SaveValuesProfileAction)
    return reg


@pytest.fixture
def profile_store() -> InMemoryProfileStore:
    return InMemoryProfileStore()


@pytest.fixture
def engine(registry, profile_store) -> WorkflowEngine:
    store = InMemoryStore()
    eng = WorkflowEngine(store, registry, extras={"__profile_store__": profile_store})
    return eng


async def _complete_pending(
    engine: WorkflowEngine, process_id: str, expected_def_id: str, output: dict
) -> None:
    """Find the single pending task with the given definition id and complete it."""
    pending = await engine.get_pending_tasks(process_id)
    assert len(pending) == 1, f"expected 1 pending task, got {len(pending)}"
    task = pending[0]
    assert task.task_definition_id == expected_def_id, (
        f"expected pending task '{expected_def_id}', got '{task.task_definition_id}'"
    )
    await engine.complete_task(task.id, TaskResult.ok(output=output))


async def _walk_text_forms(engine: WorkflowEngine, process_id: str, texts: dict) -> None:
    """Complete all four free-form text forms in order."""
    for field in ("core_values", "ethical_positions", "priorities", "deal_breakers"):
        await _complete_pending(
            engine,
            process_id,
            f"{field}_form",
            {f"{field}_text": texts[field]},
        )


async def test_wizard_capture_mode_persists_new_profile(
    engine: WorkflowEngine, definition, profile_store: InMemoryProfileStore
):
    """First-time wizard run: no existing profile, save creates version 1."""
    process = await engine.create_process(definition, properties={"user_id": 42})
    await engine.start_process(process.id)

    texts = {
        "core_values": "I value honesty and personal growth.",
        "ethical_positions": "I'm vegetarian for animal-welfare reasons.",
        "priorities": "Family first, then meaningful work, then personal projects.",
        "deal_breakers": "I would never want an AI to deceive on my behalf.",
    }
    await _walk_text_forms(engine, process.id, texts)

    # extract_tags ran auto; we should now be on the review form.
    await _complete_pending(
        engine,
        process.id,
        "review_form",
        {
            "core_values_text": texts["core_values"],
            "core_values_tags": ["honesty"],
            "ethical_positions_text": texts["ethical_positions"],
            "ethical_positions_tags": [],
            "priorities_text": texts["priorities"],
            "priorities_tags": [],
            "deal_breakers_text": texts["deal_breakers"],
            "deal_breakers_tags": ["no-deception"],
        },
    )

    final = await engine.store.load_process(process.id)
    assert final.state == ProcessState.COMPLETE

    saved = await profile_store.get_current(user_id=42)
    assert saved is not None
    assert saved.version_number == 1
    assert saved.core_values_text == texts["core_values"]
    assert saved.core_values_tags == ["honesty"]
    assert saved.deal_breakers_tags == ["no-deception"]
    # created_via comes from existing_profile.mode = "capture" because there was no prior profile.
    assert saved.created_via == "capture"


async def test_wizard_edit_mode_pre_populates_and_creates_v2(
    engine: WorkflowEngine, definition, profile_store: InMemoryProfileStore
):
    """Edit mode: existing profile pre-populates defaults; save creates version 2."""
    # Pre-seed user with an existing profile.
    await profile_store.save_version(
        user_id=42,
        version=ValuesProfileVersion(
            core_values_text="original honesty",
            core_values_tags=["honesty"],
            ethical_positions_text="original positions",
            priorities_text="original priorities",
            deal_breakers_text="original deal-breakers",
        ),
    )

    process = await engine.create_process(definition, properties={"user_id": 42})
    await engine.start_process(process.id)

    # The first pending task should be core_values_form, with the existing
    # text propagated to process properties via load_values_profile.
    pending = await engine.get_pending_tasks(process.id)
    assert pending[0].task_definition_id == "core_values_form"
    # Reload process to see properties written by load_values_profile.
    process_after_load = await engine.store.load_process(process.id)
    existing = process_after_load.properties.get("existing_profile")
    assert existing is not None
    assert existing["core_values_text"] == "original honesty"
    assert existing["core_values_tags"] == ["honesty"]

    # User updates only core_values; leaves the others as their previous text.
    texts = {
        "core_values": "updated honesty and curiosity",
        "ethical_positions": "original positions",
        "priorities": "original priorities",
        "deal_breakers": "original deal-breakers",
    }
    await _walk_text_forms(engine, process.id, texts)

    await _complete_pending(
        engine,
        process.id,
        "review_form",
        {
            "core_values_text": texts["core_values"],
            "core_values_tags": ["honesty", "curiosity"],
            "ethical_positions_text": texts["ethical_positions"],
            "ethical_positions_tags": [],
            "priorities_text": texts["priorities"],
            "priorities_tags": [],
            "deal_breakers_text": texts["deal_breakers"],
            "deal_breakers_tags": [],
        },
    )

    final = await engine.store.load_process(process.id)
    assert final.state == ProcessState.COMPLETE

    saved = await profile_store.get_current(user_id=42)
    assert saved is not None
    assert saved.version_number == 2
    assert saved.core_values_text == "updated honesty and curiosity"
    assert saved.core_values_tags == ["honesty", "curiosity"]
    assert saved.created_via == "edit"
