"""Unit tests for the data export feature (F9 / REQ-DATA-003).

Tests cover:
- DataExporter produces a valid ZIP with the expected files
- Each section contains correct JSON structure
- Export degrades gracefully when stores are None
- The /api/export/ endpoint requires authentication and returns a ZIP
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ===========================================================================
# DataExporter unit tests (no Django required)
# ===========================================================================


async def _make_export(**kwargs) -> dict:
    """Run DataExporter and return the contents of all JSON files in the ZIP."""
    from zebra_agent.export import DataExporter

    exporter = DataExporter()
    archive = await exporter.export_user_data(user_id="42", **kwargs)

    contents = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        for name in zf.namelist():
            if name.endswith(".json"):
                contents[name] = json.loads(zf.read(name))
    return contents


@pytest.mark.asyncio
async def test_export_manifest_always_present():
    """Manifest is always written with correct format_version and user_id."""
    contents = await _make_export()
    manifest = contents["manifest.json"]
    assert manifest["format_version"] == 1
    assert manifest["user_id"] == "42"
    assert "exported_at" in manifest
    assert isinstance(manifest["sections"], list)


@pytest.mark.asyncio
async def test_export_degrades_gracefully_when_all_stores_none():
    """All sections return empty lists when no stores are provided."""
    contents = await _make_export()
    assert contents["processes.json"]["processes"] == []
    assert contents["memory.json"]["workflow_memories"] == []
    assert contents["memory.json"]["conceptual_memories"] == []
    assert contents["metrics.json"]["runs"] == []
    assert contents["knowledge.json"]["entries"] == []


@pytest.mark.asyncio
async def test_export_memory_section():
    """Memory store entries appear in memory.json."""
    from zebra_agent.memory import ConceptualMemoryEntry, WorkflowMemoryEntry

    wm = WorkflowMemoryEntry(
        id="wm-1",
        timestamp=datetime(2025, 1, 1, tzinfo=UTC),
        workflow_name="My Workflow",
        goal="Test goal",
        success=True,
        input_summary="input",
        output_summary="output",
        effectiveness_notes="good",
        tokens_used=100,
    )
    cm = ConceptualMemoryEntry(
        id="cm-1",
        concept="testing",
        recommended_workflows=[],
        anti_patterns="",
        last_updated=datetime(2025, 1, 1, tzinfo=UTC),
    )

    memory_store = MagicMock()
    memory_store.get_recent_workflow_memories = AsyncMock(return_value=[wm])
    memory_store.get_conceptual_memories = AsyncMock(return_value=[cm])

    contents = await _make_export(memory_store=memory_store)
    mem = contents["memory.json"]
    assert len(mem["workflow_memories"]) == 1
    assert mem["workflow_memories"][0]["id"] == "wm-1"
    assert mem["workflow_memories"][0]["workflow_name"] == "My Workflow"
    assert len(mem["conceptual_memories"]) == 1
    assert mem["conceptual_memories"][0]["concept"] == "testing"


@pytest.mark.asyncio
async def test_export_metrics_section():
    """Metrics store runs appear in metrics.json."""
    from zebra_agent.metrics import WorkflowRun

    run = WorkflowRun(
        id="run-1",
        workflow_name="My Workflow",
        goal="Test goal",
        started_at=datetime(2025, 1, 1, tzinfo=UTC),
        completed_at=datetime(2025, 1, 1, 0, 1, tzinfo=UTC),
        success=True,
        cost=0.05,
    )

    metrics_store = MagicMock()
    metrics_store.get_recent_runs = AsyncMock(return_value=[run])

    contents = await _make_export(metrics_store=metrics_store)
    runs = contents["metrics.json"]["runs"]
    assert len(runs) == 1
    assert runs[0]["id"] == "run-1"
    assert runs[0]["success"] is True
    assert runs[0]["cost"] == 0.05


@pytest.mark.asyncio
async def test_export_knowledge_section():
    """Knowledge entries appear in knowledge.json."""
    from zebra_agent.knowledge import KnowledgeEntry

    entry = KnowledgeEntry(
        id="ke-1",
        user_id=42,
        category="preferences",
        key="theme",
        value="dark",
        source="human",
        confidence=1.0,
        last_verified=datetime(2025, 1, 1, tzinfo=UTC),
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
    )

    knowledge_store = MagicMock()
    knowledge_store.get_entries = AsyncMock(return_value=[entry])

    contents = await _make_export(knowledge_store=knowledge_store)
    entries = contents["knowledge.json"]["entries"]
    assert len(entries) == 1
    assert entries[0]["key"] == "theme"
    assert entries[0]["category"] == "preferences"


@pytest.mark.asyncio
async def test_export_workflows_section():
    """Workflow YAML files appear under workflows/ in the ZIP."""
    from zebra_agent.export import DataExporter

    wf = MagicMock()
    wf.name = "My Workflow"

    library = MagicMock()
    library.list_workflows = AsyncMock(return_value=[wf])
    library.get_workflow_yaml = MagicMock(return_value="name: My Workflow\n")

    exporter = DataExporter()
    archive = await exporter.export_user_data(user_id="42", workflow_library=library)

    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        names = zf.namelist()
        assert "workflows/My Workflow.yaml" in names
        yaml_content = zf.read("workflows/My Workflow.yaml").decode()
        assert "My Workflow" in yaml_content

    manifest_raw = json.loads(zipfile.ZipFile(io.BytesIO(archive)).read("manifest.json"))
    assert "workflows" in manifest_raw["sections"]


@pytest.mark.asyncio
async def test_export_produces_valid_zip():
    """The archive is a valid ZIP file with at least manifest.json."""
    from zebra_agent.export import DataExporter

    exporter = DataExporter()
    archive = await exporter.export_user_data(user_id="1")
    assert zipfile.is_zipfile(io.BytesIO(archive))

    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        assert "manifest.json" in zf.namelist()


# ===========================================================================
# API endpoint tests (requires Django test DB)
# ===========================================================================


@pytest.mark.django_db
def test_export_endpoint_requires_authentication(client):
    """GET /api/export/ without login returns 403."""
    response = client.get("/api/export/")
    # DRF returns 403 for unauthenticated requests when IsAuthenticated is set
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_export_endpoint_returns_zip(authenticated_client):
    """GET /api/export/ while authenticated returns a ZIP file download."""
    archive_bytes = b"PK" + b"\x00" * 20  # minimal fake ZIP header

    with patch(
        "zebra_agent_web.api.views._export_data_impl",
        return_value=archive_bytes,
    ):
        response = authenticated_client.get("/api/export/")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    assert "attachment" in response["Content-Disposition"]
    assert "zebra-export-" in response["Content-Disposition"]
    assert response.content == archive_bytes


@pytest.mark.django_db
def test_export_endpoint_error_returns_500(authenticated_client):
    """When DataExporter raises, the endpoint returns 500 with an error message."""
    with patch(
        "zebra_agent_web.api.views._export_data_impl",
        side_effect=RuntimeError("store unavailable"),
    ):
        response = authenticated_client.get("/api/export/")

    assert response.status_code == 500
    body = response.json()
    assert "error" in body
    assert "store unavailable" in body["error"]
