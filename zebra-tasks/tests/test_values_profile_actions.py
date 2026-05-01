"""Tests for the F18 values-profile task actions.

Mocks ``ProfileStore`` and the LLM provider so tests run without a database
connection or LLM credentials.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zebra_agent.profile import ValuesProfileVersion
from zebra_agent.storage.profile import InMemoryProfileStore

from zebra_tasks.agent.extract_values_tags import ExtractValuesTagsAction
from zebra_tasks.agent.load_values_profile import LoadValuesProfileAction
from zebra_tasks.agent.save_values_profile import SaveValuesProfileAction


@pytest.fixture
def mock_task():
    task = MagicMock()
    task.id = "task-1"
    task.properties = {}
    return task


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.process = MagicMock()
    context.process.id = "process-1"
    context.process.properties = {}
    context.extras = {}
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    return context


# ---------------------------------------------------------------------------
# LoadValuesProfileAction
# ---------------------------------------------------------------------------


async def test_load_capture_mode_when_no_profile(mock_task, mock_context):
    store = InMemoryProfileStore()
    mock_context.extras["__profile_store__"] = store
    mock_task.properties = {"user_id": 42}

    result = await LoadValuesProfileAction().run(mock_task, mock_context)

    assert result.success
    assert result.output == {"found": False, "mode": "capture"}
    saved = mock_context.process.properties["existing_profile"]
    assert saved["core_values_text"] == ""
    assert saved["core_values_tags"] == []


async def test_load_edit_mode_when_profile_exists(mock_task, mock_context):
    store = InMemoryProfileStore()
    await store.save_version(
        user_id=42,
        version=ValuesProfileVersion(
            core_values_text="honesty",
            core_values_tags=["honesty"],
            deal_breakers_text="no harm",
        ),
    )
    mock_context.extras["__profile_store__"] = store
    mock_task.properties = {"user_id": 42}

    result = await LoadValuesProfileAction().run(mock_task, mock_context)

    assert result.success
    assert result.output == {"found": True, "mode": "edit"}
    saved = mock_context.process.properties["existing_profile"]
    assert saved["core_values_text"] == "honesty"
    assert saved["core_values_tags"] == ["honesty"]
    assert saved["deal_breakers_text"] == "no harm"


async def test_load_degrades_when_no_store(mock_task, mock_context):
    mock_task.properties = {"user_id": 42}

    result = await LoadValuesProfileAction().run(mock_task, mock_context)

    assert result.success
    assert result.output == {"found": False, "mode": "capture"}


async def test_load_fails_without_user_id(mock_task, mock_context):
    mock_task.properties = {}

    result = await LoadValuesProfileAction().run(mock_task, mock_context)

    assert not result.success
    assert "user_id" in (result.error or "")


# ---------------------------------------------------------------------------
# ExtractValuesTagsAction
# ---------------------------------------------------------------------------


def _llm_response(payload: dict) -> MagicMock:
    return MagicMock(
        content=json.dumps(payload),
        model="claude-haiku",
        usage=MagicMock(input_tokens=100, output_tokens=50, total_tokens=150),
    )


def _llm_provider(response: MagicMock) -> MagicMock:
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=response)
    return provider


async def test_extract_returns_empty_when_no_store(mock_task, mock_context):
    mock_task.properties = {"core_values_text": "honesty"}

    result = await ExtractValuesTagsAction().run(mock_task, mock_context)

    assert result.success
    extracted = mock_context.process.properties["extracted_tags"]
    for field in ("core_values", "ethical_positions", "priorities", "deal_breakers"):
        assert extracted[field] == {"approved_tags": [], "candidate_tags": []}


async def test_extract_returns_empty_when_llm_fails(mock_task, mock_context):
    store = InMemoryProfileStore()
    store.seed_tag("core_values", "honesty", "Honesty")
    mock_context.extras["__profile_store__"] = store
    mock_task.properties = {"core_values_text": "I value honesty"}

    failing = MagicMock()
    failing.complete = AsyncMock(side_effect=RuntimeError("network down"))

    with patch("zebra_tasks.agent.extract_values_tags.get_provider", return_value=failing):
        result = await ExtractValuesTagsAction().run(mock_task, mock_context)

    assert result.success
    extracted = mock_context.process.properties["extracted_tags"]
    assert extracted["core_values"] == {"approved_tags": [], "candidate_tags": []}


async def test_extract_parses_approved_and_candidate_tags(mock_task, mock_context):
    store = InMemoryProfileStore()
    store.seed_tag("core_values", "honesty", "Honesty")
    store.seed_tag("core_values", "growth", "Growth")
    store.seed_tag("deal_breakers", "no-deception", "No deception")
    mock_context.extras["__profile_store__"] = store
    mock_task.properties = {
        "core_values_text": "honesty and intellectual curiosity",
        "deal_breakers_text": "no lying ever",
    }

    payload = {
        "core_values": {
            "approved_tags": ["honesty"],
            "candidate_tags": [
                {"slug": "intellectual-curiosity", "label": "Intellectual Curiosity"},
            ],
        },
        "ethical_positions": {"approved_tags": [], "candidate_tags": []},
        "priorities": {"approved_tags": [], "candidate_tags": []},
        "deal_breakers": {
            "approved_tags": ["no-deception"],
            "candidate_tags": [],
        },
    }

    with patch(
        "zebra_tasks.agent.extract_values_tags.get_provider",
        return_value=_llm_provider(_llm_response(payload)),
    ):
        result = await ExtractValuesTagsAction().run(mock_task, mock_context)

    assert result.success
    extracted = mock_context.process.properties["extracted_tags"]
    assert extracted["core_values"]["approved_tags"] == ["honesty"]
    assert extracted["core_values"]["candidate_tags"] == [
        {"slug": "intellectual-curiosity", "label": "Intellectual Curiosity"}
    ]
    assert extracted["deal_breakers"]["approved_tags"] == ["no-deception"]


async def test_extract_drops_unknown_approved_tags(mock_task, mock_context):
    """LLM-hallucinated approved tags (not in the store) must be dropped."""
    store = InMemoryProfileStore()
    store.seed_tag("core_values", "honesty", "Honesty")
    mock_context.extras["__profile_store__"] = store
    mock_task.properties = {"core_values_text": "honesty"}

    payload = {
        "core_values": {
            "approved_tags": ["honesty", "made-up-tag"],
            "candidate_tags": [],
        },
        "ethical_positions": {"approved_tags": [], "candidate_tags": []},
        "priorities": {"approved_tags": [], "candidate_tags": []},
        "deal_breakers": {"approved_tags": [], "candidate_tags": []},
    }

    with patch(
        "zebra_tasks.agent.extract_values_tags.get_provider",
        return_value=_llm_provider(_llm_response(payload)),
    ):
        await ExtractValuesTagsAction().run(mock_task, mock_context)

    extracted = mock_context.process.properties["extracted_tags"]
    assert extracted["core_values"]["approved_tags"] == ["honesty"]


async def test_extract_caps_candidates_to_five(mock_task, mock_context):
    store = InMemoryProfileStore()
    mock_context.extras["__profile_store__"] = store
    mock_task.properties = {"core_values_text": "lots of things"}

    payload = {
        "core_values": {
            "approved_tags": [],
            "candidate_tags": [{"slug": f"tag-{i}", "label": f"Tag {i}"} for i in range(10)],
        },
        "ethical_positions": {"approved_tags": [], "candidate_tags": []},
        "priorities": {"approved_tags": [], "candidate_tags": []},
        "deal_breakers": {"approved_tags": [], "candidate_tags": []},
    }

    with patch(
        "zebra_tasks.agent.extract_values_tags.get_provider",
        return_value=_llm_provider(_llm_response(payload)),
    ):
        await ExtractValuesTagsAction().run(mock_task, mock_context)

    extracted = mock_context.process.properties["extracted_tags"]
    assert len(extracted["core_values"]["candidate_tags"]) == 5


# ---------------------------------------------------------------------------
# SaveValuesProfileAction
# ---------------------------------------------------------------------------


async def test_save_persists_version_and_tags(mock_task, mock_context):
    store = InMemoryProfileStore()
    mock_context.extras["__profile_store__"] = store
    mock_task.properties = {
        "user_id": 1,
        "extraction_model": "claude-haiku",
        "confirmed": {
            "core_values": {
                "text": "honesty and growth",
                "tags": [
                    {"slug": "honesty", "label": "Honesty"},
                    {"slug": "growth", "label": "Growth"},
                ],
            },
            "ethical_positions": {"text": "", "tags": []},
            "priorities": {"text": "family first", "tags": [{"slug": "family", "label": "Family"}]},
            "deal_breakers": {
                "text": "no deception",
                "tags": [{"slug": "no-deception", "label": "No deception"}],
            },
        },
    }

    result = await SaveValuesProfileAction().run(mock_task, mock_context)

    assert result.success
    assert result.output["version_number"] == 1
    assert result.output["version_id"]

    current = await store.get_current(user_id=1)
    assert current is not None
    assert current.core_values_text == "honesty and growth"
    assert current.core_values_tags == ["honesty", "growth"]
    assert current.priorities_tags == ["family"]
    assert current.tags_extraction_model == "claude-haiku"

    # Tag rows accumulated as candidates with usage_count = 1.
    core_tags = await store.get_approved_tags("core_values")
    assert core_tags == []  # all are still candidate, not approved
    # But internal state knows about them (verify via direct internal lookup).
    assert "honesty" in store._tags["core_values"]
    assert store._tags["core_values"]["honesty"]["usage_count"] == 1


async def test_save_increments_usage_count_on_repeat(mock_task, mock_context):
    store = InMemoryProfileStore()
    mock_context.extras["__profile_store__"] = store
    base_props = {
        "user_id": 1,
        "confirmed": {
            "core_values": {"text": "honesty", "tags": [{"slug": "honesty", "label": "Honesty"}]},
            "ethical_positions": {"text": "", "tags": []},
            "priorities": {"text": "", "tags": []},
            "deal_breakers": {"text": "", "tags": []},
        },
    }
    mock_task.properties = base_props
    await SaveValuesProfileAction().run(mock_task, mock_context)

    # Second save with the same tag should increment usage_count.
    mock_task.properties = base_props
    await SaveValuesProfileAction().run(mock_task, mock_context)

    assert store._tags["core_values"]["honesty"]["usage_count"] == 2


async def test_save_fails_without_store(mock_task, mock_context):
    mock_task.properties = {
        "user_id": 1,
        "confirmed": {
            field: {"text": "", "tags": []}
            for field in ["core_values", "ethical_positions", "priorities", "deal_breakers"]
        },
    }

    result = await SaveValuesProfileAction().run(mock_task, mock_context)

    assert not result.success


async def test_save_fails_with_invalid_user_id(mock_task, mock_context):
    store = InMemoryProfileStore()
    mock_context.extras["__profile_store__"] = store
    mock_task.properties = {"user_id": "not-a-number", "confirmed": {}}

    result = await SaveValuesProfileAction().run(mock_task, mock_context)

    assert not result.success
    assert "user_id" in (result.error or "").lower()
