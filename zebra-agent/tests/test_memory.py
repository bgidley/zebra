"""Tests for the memory module.

Tests the new workflow-focused two-tier memory system:
- WorkflowMemoryEntry: Detailed per-run records
- ConceptualMemoryEntry: Compact goal-pattern index
"""

from datetime import UTC, datetime

from zebra_agent.memory import (
    ConceptualMemoryEntry,
    WorkflowMemoryEntry,
    estimate_tokens,
)


class TestWorkflowMemoryEntry:
    """Tests for WorkflowMemoryEntry dataclass."""

    def test_create_entry(self):
        """Test creating a workflow memory entry."""
        entry = WorkflowMemoryEntry(
            id="test-id",
            timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            workflow_name="TestWorkflow",
            goal="Test goal",
            success=True,
            input_summary="Input",
            output_summary="Output",
            effectiveness_notes="Worked well",
            tokens_used=100,
        )
        assert entry.id == "test-id"
        assert entry.workflow_name == "TestWorkflow"
        assert entry.goal == "Test goal"
        assert entry.success is True
        assert entry.tokens_used == 100
        assert entry.rating is None

    def test_create_via_factory(self):
        """Test creating entry via factory method."""
        entry = WorkflowMemoryEntry.create(
            workflow_name="MyWorkflow",
            goal="My goal",
            success=False,
            input_summary="Some input",
            output_summary="Some output",
            effectiveness_notes="Failed halfway",
            tokens_used=50,
            rating=2,
        )
        assert entry.id  # Auto-generated
        assert entry.timestamp  # Auto-set
        assert entry.workflow_name == "MyWorkflow"
        assert entry.success is False
        assert entry.rating == 2

    def test_to_dict(self):
        """Test converting entry to dictionary."""
        entry = WorkflowMemoryEntry(
            id="test-id",
            timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            workflow_name="TestWorkflow",
            goal="Test goal",
            success=True,
            input_summary="Input",
            output_summary="Output",
            effectiveness_notes="Notes",
            tokens_used=100,
        )
        data = entry.to_dict()
        assert data["id"] == "test-id"
        assert data["workflow_name"] == "TestWorkflow"
        assert data["timestamp"] == "2024-01-15T10:30:00+00:00"
        assert data["success"] is True

    def test_from_dict(self):
        """Test creating entry from dictionary."""
        data = {
            "id": "test-id",
            "timestamp": "2024-01-15T10:30:00+00:00",
            "workflow_name": "TestWorkflow",
            "goal": "Test goal",
            "success": True,
            "input_summary": "Input",
            "output_summary": "Output",
            "effectiveness_notes": "Notes",
            "tokens_used": 100,
        }
        entry = WorkflowMemoryEntry.from_dict(data)
        assert entry.id == "test-id"
        assert entry.timestamp == datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        assert entry.workflow_name == "TestWorkflow"
        assert entry.tokens_used == 100


class TestConceptualMemoryEntry:
    """Tests for ConceptualMemoryEntry dataclass."""

    def test_create_entry(self):
        """Test creating a conceptual memory entry."""
        entry = ConceptualMemoryEntry.create(
            concept="code analysis tasks",
            recommended_workflows=[
                {
                    "name": "analyze_code",
                    "fit_notes": "Good for analysis",
                    "avg_rating": 4.0,
                    "use_count": 5,
                }
            ],
            anti_patterns="Don't use for simple questions",
        )
        assert entry.id
        assert entry.concept == "code analysis tasks"
        assert len(entry.recommended_workflows) == 1
        assert entry.anti_patterns == "Don't use for simple questions"

    def test_to_dict(self):
        """Test converting to dictionary."""
        entry = ConceptualMemoryEntry(
            id="cme-1",
            concept="writing assistance",
            recommended_workflows=[
                {"name": "write_docs", "fit_notes": "Great", "avg_rating": None, "use_count": 3}
            ],
            anti_patterns="Not for code",
            last_updated=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
            tokens=50,
        )
        data = entry.to_dict()
        assert data["id"] == "cme-1"
        assert data["concept"] == "writing assistance"
        assert data["last_updated"] == "2024-01-15T10:00:00+00:00"

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "id": "cme-1",
            "concept": "writing assistance",
            "recommended_workflows": [
                {"name": "write_docs", "fit_notes": "Great", "avg_rating": None, "use_count": 3}
            ],
            "anti_patterns": "Not for code",
            "last_updated": "2024-01-15T10:00:00+00:00",
            "tokens": 50,
        }
        entry = ConceptualMemoryEntry.from_dict(data)
        assert entry.id == "cme-1"
        assert entry.concept == "writing assistance"
        assert len(entry.recommended_workflows) == 1


class TestInMemoryMemoryStore:
    """Tests for InMemoryMemoryStore (new interface)."""

    async def test_initialization(self, memory):
        """Test that memory initializes correctly."""
        await memory._ensure_initialized()
        assert memory._initialized is True

    async def test_double_initialization(self, memory):
        """Test that double initialization is safe."""
        await memory._ensure_initialized()
        await memory._ensure_initialized()
        assert memory._initialized is True

    # ── Workflow Memory ────────────────────────────────────────────────────────

    async def test_add_workflow_memory(self, memory):
        """Test adding a workflow memory entry."""
        entry = WorkflowMemoryEntry.create(
            workflow_name="MyWorkflow",
            goal="My goal",
            success=True,
            input_summary="input",
            output_summary="output",
            effectiveness_notes="Good",
            tokens_used=100,
        )
        await memory.add_workflow_memory(entry)

        entries = await memory.get_recent_workflow_memories(limit=10)
        assert len(entries) == 1
        assert entries[0].id == entry.id

    async def test_get_workflow_memories_filtered(self, memory):
        """Test getting workflow memories for a specific workflow."""
        e1 = WorkflowMemoryEntry.create(
            workflow_name="WorkflowA",
            goal="g1",
            success=True,
            input_summary="i",
            output_summary="o",
            effectiveness_notes="",
            tokens_used=0,
        )
        e2 = WorkflowMemoryEntry.create(
            workflow_name="WorkflowB",
            goal="g2",
            success=False,
            input_summary="i",
            output_summary="o",
            effectiveness_notes="",
            tokens_used=0,
        )
        await memory.add_workflow_memory(e1)
        await memory.add_workflow_memory(e2)

        a_entries = await memory.get_workflow_memories("WorkflowA")
        assert len(a_entries) == 1
        assert a_entries[0].workflow_name == "WorkflowA"

        b_entries = await memory.get_workflow_memories("WorkflowB")
        assert len(b_entries) == 1
        assert b_entries[0].workflow_name == "WorkflowB"

    async def test_get_recent_workflow_memories_newest_first(self, memory):
        """Test that recent entries are returned newest first."""
        from datetime import timedelta

        base_time = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        e1 = WorkflowMemoryEntry(
            id="e1",
            timestamp=base_time,
            workflow_name="W",
            goal="g",
            success=True,
            input_summary="i",
            output_summary="o",
            effectiveness_notes="",
            tokens_used=0,
        )
        e2 = WorkflowMemoryEntry(
            id="e2",
            timestamp=base_time + timedelta(hours=1),
            workflow_name="W",
            goal="g",
            success=True,
            input_summary="i",
            output_summary="o",
            effectiveness_notes="",
            tokens_used=0,
        )
        await memory.add_workflow_memory(e1)
        await memory.add_workflow_memory(e2)

        entries = await memory.get_recent_workflow_memories(limit=10)
        assert entries[0].id == "e2"  # Newest first
        assert entries[1].id == "e1"

    # ── Conceptual Memory ─────────────────────────────────────────────────────

    async def test_save_and_get_conceptual_memory(self, memory):
        """Test saving and retrieving conceptual memory."""
        entry = ConceptualMemoryEntry.create(
            concept="code tasks",
            recommended_workflows=[
                {"name": "analyze_code", "fit_notes": "good", "avg_rating": None, "use_count": 1}
            ],
            anti_patterns="",
        )
        await memory.save_conceptual_memory(entry)

        entries = await memory.get_conceptual_memories()
        assert len(entries) == 1
        assert entries[0].concept == "code tasks"

    async def test_save_conceptual_memory_updates_existing(self, memory):
        """Test that saving an entry with the same ID updates it."""
        entry = ConceptualMemoryEntry.create(concept="writing")
        await memory.save_conceptual_memory(entry)

        updated = ConceptualMemoryEntry(
            id=entry.id,
            concept="writing (updated)",
            recommended_workflows=[],
            anti_patterns="nothing",
            last_updated=datetime.now(UTC),
            tokens=10,
        )
        await memory.save_conceptual_memory(updated)

        entries = await memory.get_conceptual_memories()
        assert len(entries) == 1  # Not duplicated
        assert entries[0].concept == "writing (updated)"

    async def test_clear_conceptual_memories(self, memory):
        """Test clearing all conceptual memories."""
        await memory.save_conceptual_memory(ConceptualMemoryEntry.create(concept="a"))
        await memory.save_conceptual_memory(ConceptualMemoryEntry.create(concept="b"))
        assert len(await memory.get_conceptual_memories()) == 2

        await memory.clear_conceptual_memories()
        assert len(await memory.get_conceptual_memories()) == 0

    async def test_get_conceptual_context_for_llm_empty(self, memory):
        """Test context generation when memory is empty."""
        context = await memory.get_conceptual_context_for_llm()
        assert context == ""

    async def test_get_conceptual_context_for_llm_with_entries(self, memory):
        """Test context generation with entries."""
        entry = ConceptualMemoryEntry.create(
            concept="code analysis",
            recommended_workflows=[
                {
                    "name": "analyze_code",
                    "fit_notes": "Best for analysis",
                    "avg_rating": 4.5,
                    "use_count": 3,
                }
            ],
            anti_patterns="Don't use for writing",
        )
        await memory.save_conceptual_memory(entry)

        context = await memory.get_conceptual_context_for_llm()
        assert "code analysis" in context
        assert "analyze_code" in context
        assert "Best for analysis" in context
        assert "Don't use for writing" in context

    async def test_get_workflow_context_for_llm_empty(self, memory):
        """Test workflow context generation when no entries exist."""
        context = await memory.get_workflow_context_for_llm("NonExistent")
        assert context == ""

    async def test_get_workflow_context_for_llm_with_entries(self, memory):
        """Test workflow context generation with entries."""
        entry = WorkflowMemoryEntry.create(
            workflow_name="analyze_code",
            goal="Analyze my Python module",
            success=True,
            input_summary="Python module",
            output_summary="Found 3 issues",
            effectiveness_notes="Clear and precise",
            tokens_used=500,
        )
        await memory.add_workflow_memory(entry)

        context = await memory.get_workflow_context_for_llm("analyze_code")
        assert "analyze_code" in context
        assert "Analyze my Python module" in context

    async def test_get_stats(self, memory):
        """Test getting memory statistics."""
        stats = await memory.get_stats()
        assert stats["workflow_memory_entries"] == 0
        assert stats["conceptual_memory_entries"] == 0

        await memory.add_workflow_memory(
            WorkflowMemoryEntry.create(
                workflow_name="W",
                goal="g",
                success=True,
                input_summary="i",
                output_summary="o",
                effectiveness_notes="",
                tokens_used=0,
            )
        )
        await memory.save_conceptual_memory(ConceptualMemoryEntry.create(concept="c"))

        stats = await memory.get_stats()
        assert stats["workflow_memory_entries"] == 1
        assert stats["conceptual_memory_entries"] == 1


class TestEstimateTokens:
    """Test token estimation."""

    def test_estimate_tokens(self):
        text = "1234" * 10  # 40 chars
        assert estimate_tokens(text) == 10

        text = ""
        assert estimate_tokens(text) == 0
