"""Tests for the memory module."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from zebra_agent.memory import (
    AgentMemory,
    LongTermTheme,
    MemoryEntry,
    ShortTermSummary,
    estimate_tokens,
)


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)
    # Cleanup
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def memory(temp_db):
    """Create an AgentMemory instance with small limits for testing."""
    return AgentMemory(
        temp_db,
        short_term_max_tokens=1000,
        long_term_max_tokens=2000,
        compact_threshold=0.9,
    )


class TestMemoryEntry:
    """Tests for MemoryEntry dataclass."""

    def test_create_entry(self):
        """Test creating a memory entry."""
        entry = MemoryEntry(
            id="test-id",
            timestamp=datetime(2024, 1, 15, 10, 30),
            goal="Test goal",
            workflow_used="TestWorkflow",
            result_summary="Test result",
            tokens=100,
        )
        assert entry.id == "test-id"
        assert entry.goal == "Test goal"
        assert entry.tokens == 100

    def test_to_dict(self):
        """Test converting entry to dictionary."""
        entry = MemoryEntry(
            id="test-id",
            timestamp=datetime(2024, 1, 15, 10, 30),
            goal="Test goal",
            workflow_used="TestWorkflow",
            result_summary="Test result",
            tokens=100,
        )
        data = entry.to_dict()
        assert data["id"] == "test-id"
        assert data["goal"] == "Test goal"
        assert data["timestamp"] == "2024-01-15T10:30:00"

    def test_from_dict(self):
        """Test creating entry from dictionary."""
        data = {
            "id": "test-id",
            "timestamp": "2024-01-15T10:30:00",
            "goal": "Test goal",
            "workflow_used": "TestWorkflow",
            "result_summary": "Test result",
            "tokens": 100,
        }
        entry = MemoryEntry.from_dict(data)
        assert entry.id == "test-id"
        assert entry.goal == "Test goal"
        assert entry.timestamp == datetime(2024, 1, 15, 10, 30)


class TestShortTermSummary:
    """Tests for ShortTermSummary dataclass."""

    def test_create_summary(self):
        """Test creating a short-term summary."""
        summary = ShortTermSummary(
            id="sum-1",
            created_at=datetime(2024, 1, 15, 12, 0),
            summary="This is a summary of recent interactions.",
            tokens=50,
            entry_count=5,
        )
        assert summary.id == "sum-1"
        assert summary.entry_count == 5
        assert summary.tokens == 50


class TestLongTermTheme:
    """Tests for LongTermTheme dataclass."""

    def test_create_theme(self):
        """Test creating a long-term theme."""
        theme = LongTermTheme(
            id="theme-1",
            created_at=datetime(2024, 1, 15, 14, 0),
            theme="User prefers Python and async patterns.",
            tokens=30,
            short_term_refs=["sum-1", "sum-2"],
        )
        assert theme.id == "theme-1"
        assert len(theme.short_term_refs) == 2
        assert "sum-1" in theme.short_term_refs


class TestEstimateTokens:
    """Tests for the estimate_tokens function."""

    def test_empty_string(self):
        """Test token estimation for empty string."""
        assert estimate_tokens("") == 0

    def test_short_string(self):
        """Test token estimation for short string."""
        assert estimate_tokens("test") == 1  # 4 chars / 4 = 1

    def test_longer_string(self):
        """Test token estimation for longer string."""
        text = "a" * 100
        assert estimate_tokens(text) == 25  # 100 / 4 = 25


class TestAgentMemoryInitialization:
    """Tests for AgentMemory initialization."""

    async def test_initialization(self, memory):
        """Test that memory initializes correctly."""
        await memory._ensure_initialized()
        assert memory._initialized is True

    async def test_creates_directory(self, temp_db):
        """Test that memory creates parent directories."""
        nested_path = temp_db.parent / "subdir" / "memory.db"
        memory = AgentMemory(nested_path)
        await memory._ensure_initialized()
        assert nested_path.parent.exists()
        # Cleanup
        nested_path.unlink(missing_ok=True)
        nested_path.parent.rmdir()


class TestShortTermMemory:
    """Tests for short-term memory operations."""

    async def test_add_entry(self, memory):
        """Test adding an entry to short-term memory."""
        entry = MemoryEntry(
            id="entry-1",
            timestamp=datetime.now(),
            goal="Test goal",
            workflow_used="TestWorkflow",
            result_summary="Test result",
            tokens=100,
        )
        await memory.add_entry(entry)

        entries = await memory.get_short_term_entries()
        assert len(entries) == 1
        assert entries[0].id == "entry-1"

    async def test_add_multiple_entries(self, memory):
        """Test adding multiple entries."""
        for i in range(5):
            entry = MemoryEntry(
                id=f"entry-{i}",
                timestamp=datetime.now(),
                goal=f"Goal {i}",
                workflow_used="TestWorkflow",
                result_summary=f"Result {i}",
                tokens=50,
            )
            await memory.add_entry(entry)

        entries = await memory.get_short_term_entries()
        assert len(entries) == 5

    async def test_get_entries_with_limit(self, memory):
        """Test getting entries with a limit."""
        for i in range(10):
            entry = MemoryEntry(
                id=f"entry-{i}",
                timestamp=datetime.now(),
                goal=f"Goal {i}",
                workflow_used="TestWorkflow",
                result_summary=f"Result {i}",
                tokens=10,
            )
            await memory.add_entry(entry)

        entries = await memory.get_short_term_entries(limit=3)
        assert len(entries) == 3

    async def test_get_short_term_tokens(self, memory):
        """Test getting total short-term tokens."""
        entry = MemoryEntry(
            id="entry-1",
            timestamp=datetime.now(),
            goal="Test goal",
            workflow_used="TestWorkflow",
            result_summary="Test result",
            tokens=100,
        )
        await memory.add_entry(entry)

        total = await memory.get_short_term_tokens()
        assert total == 100

    async def test_needs_short_term_compaction_false(self, memory):
        """Test compaction check when under threshold."""
        entry = MemoryEntry(
            id="entry-1",
            timestamp=datetime.now(),
            goal="Test goal",
            workflow_used="TestWorkflow",
            result_summary="Test result",
            tokens=100,
        )
        await memory.add_entry(entry)

        needs = await memory.needs_short_term_compaction()
        assert needs is False

    async def test_needs_short_term_compaction_true(self, memory):
        """Test compaction check when over threshold."""
        # Add entries that exceed 90% of 1000 tokens
        entry = MemoryEntry(
            id="entry-1",
            timestamp=datetime.now(),
            goal="Test goal",
            workflow_used="TestWorkflow",
            result_summary="Test result",
            tokens=950,
        )
        await memory.add_entry(entry)

        needs = await memory.needs_short_term_compaction()
        assert needs is True

    async def test_clear_short_term_entries(self, memory):
        """Test clearing short-term entries."""
        entry = MemoryEntry(
            id="entry-1",
            timestamp=datetime.now(),
            goal="Test goal",
            workflow_used="TestWorkflow",
            result_summary="Test result",
            tokens=100,
        )
        await memory.add_entry(entry)

        await memory.clear_short_term_entries()

        entries = await memory.get_short_term_entries()
        assert len(entries) == 0

    async def test_get_short_term_content_for_compaction(self, memory):
        """Test getting content for compaction."""
        entry = MemoryEntry(
            id="entry-1",
            timestamp=datetime.now(),
            goal="Test goal",
            workflow_used="TestWorkflow",
            result_summary="Test result",
            tokens=100,
        )
        await memory.add_entry(entry)

        content = await memory.get_short_term_content_for_compaction()
        assert "Test goal" in content
        assert "TestWorkflow" in content
        assert "Test result" in content


class TestShortTermSummaries:
    """Tests for short-term summary operations."""

    async def test_add_short_term_summary(self, memory):
        """Test adding a short-term summary."""
        summary = ShortTermSummary(
            id="sum-1",
            created_at=datetime.now(),
            summary="Summary of interactions",
            tokens=50,
            entry_count=5,
        )
        await memory.add_short_term_summary(summary)

        summaries = await memory.get_short_term_summaries()
        assert len(summaries) == 1
        assert summaries[0].id == "sum-1"

    async def test_get_short_term_summary_tokens(self, memory):
        """Test getting total summary tokens."""
        summary = ShortTermSummary(
            id="sum-1",
            created_at=datetime.now(),
            summary="Summary",
            tokens=50,
            entry_count=5,
        )
        await memory.add_short_term_summary(summary)

        total = await memory.get_short_term_summary_tokens()
        assert total == 50

    async def test_get_short_term_summary_by_id(self, memory):
        """Test getting a summary by ID."""
        summary = ShortTermSummary(
            id="sum-1",
            created_at=datetime.now(),
            summary="Summary",
            tokens=50,
            entry_count=5,
        )
        await memory.add_short_term_summary(summary)

        found = await memory.get_short_term_summary_by_id("sum-1")
        assert found is not None
        assert found.id == "sum-1"

    async def test_get_short_term_summary_by_id_not_found(self, memory):
        """Test getting a non-existent summary."""
        found = await memory.get_short_term_summary_by_id("nonexistent")
        assert found is None

    async def test_clear_short_term_summaries(self, memory):
        """Test clearing all summaries."""
        for i in range(3):
            summary = ShortTermSummary(
                id=f"sum-{i}",
                created_at=datetime.now(),
                summary=f"Summary {i}",
                tokens=50,
                entry_count=5,
            )
            await memory.add_short_term_summary(summary)

        await memory.clear_short_term_summaries()

        summaries = await memory.get_short_term_summaries()
        assert len(summaries) == 0

    async def test_clear_short_term_summaries_keep_ids(self, memory):
        """Test clearing summaries while keeping some."""
        for i in range(3):
            summary = ShortTermSummary(
                id=f"sum-{i}",
                created_at=datetime.now(),
                summary=f"Summary {i}",
                tokens=50,
                entry_count=5,
            )
            await memory.add_short_term_summary(summary)

        await memory.clear_short_term_summaries(keep_ids=["sum-1"])

        summaries = await memory.get_short_term_summaries()
        assert len(summaries) == 1
        assert summaries[0].id == "sum-1"


class TestLongTermMemory:
    """Tests for long-term memory operations."""

    async def test_add_long_term_theme(self, memory):
        """Test adding a long-term theme."""
        theme = LongTermTheme(
            id="theme-1",
            created_at=datetime.now(),
            theme="User preferences and patterns",
            tokens=30,
            short_term_refs=["sum-1"],
        )
        await memory.add_long_term_theme(theme)

        themes = await memory.get_long_term_themes()
        assert len(themes) == 1
        assert themes[0].id == "theme-1"

    async def test_get_long_term_tokens(self, memory):
        """Test getting total long-term tokens."""
        theme = LongTermTheme(
            id="theme-1",
            created_at=datetime.now(),
            theme="Theme",
            tokens=30,
            short_term_refs=[],
        )
        await memory.add_long_term_theme(theme)

        total = await memory.get_long_term_tokens()
        assert total == 30

    async def test_needs_long_term_compaction_false(self, memory):
        """Test long-term compaction check when under threshold."""
        theme = LongTermTheme(
            id="theme-1",
            created_at=datetime.now(),
            theme="Theme",
            tokens=100,
            short_term_refs=[],
        )
        await memory.add_long_term_theme(theme)

        needs = await memory.needs_long_term_compaction()
        assert needs is False

    async def test_needs_long_term_compaction_true(self, memory):
        """Test long-term compaction check when over threshold."""
        # Add summaries and themes that exceed 90% of 2000 tokens
        summary = ShortTermSummary(
            id="sum-1",
            created_at=datetime.now(),
            summary="Summary",
            tokens=1000,
            entry_count=10,
        )
        await memory.add_short_term_summary(summary)

        theme = LongTermTheme(
            id="theme-1",
            created_at=datetime.now(),
            theme="Theme",
            tokens=900,
            short_term_refs=["sum-1"],
        )
        await memory.add_long_term_theme(theme)

        needs = await memory.needs_long_term_compaction()
        assert needs is True

    async def test_get_long_term_content_for_compaction(self, memory):
        """Test getting content for long-term compaction."""
        summary = ShortTermSummary(
            id="sum-1",
            created_at=datetime.now(),
            summary="Detailed summary",
            tokens=50,
            entry_count=5,
        )
        await memory.add_short_term_summary(summary)

        theme = LongTermTheme(
            id="theme-1",
            created_at=datetime.now(),
            theme="Existing theme",
            tokens=30,
            short_term_refs=["sum-1"],
        )
        await memory.add_long_term_theme(theme)

        content = await memory.get_long_term_content_for_compaction()
        assert "Existing theme" in content
        assert "Detailed summary" in content

    async def test_theme_short_term_refs_serialization(self, memory):
        """Test that short_term_refs are properly serialized/deserialized."""
        refs = ["sum-1", "sum-2", "sum-3"]
        theme = LongTermTheme(
            id="theme-1",
            created_at=datetime.now(),
            theme="Theme with refs",
            tokens=30,
            short_term_refs=refs,
        )
        await memory.add_long_term_theme(theme)

        themes = await memory.get_long_term_themes()
        assert themes[0].short_term_refs == refs


class TestCombinedContext:
    """Tests for combined context operations."""

    async def test_get_context_for_llm_empty(self, memory):
        """Test getting context when memory is empty."""
        context = await memory.get_context_for_llm()
        assert context == "No previous context."

    async def test_get_context_for_llm_with_entries(self, memory):
        """Test getting context with entries."""
        entry = MemoryEntry(
            id="entry-1",
            timestamp=datetime.now(),
            goal="Test goal",
            workflow_used="TestWorkflow",
            result_summary="Test result",
            tokens=100,
        )
        await memory.add_entry(entry)

        context = await memory.get_context_for_llm()
        assert "Recent interactions" in context
        assert "Test goal" in context

    async def test_get_context_for_llm_with_all_types(self, memory):
        """Test getting context with all memory types."""
        # Add entry
        entry = MemoryEntry(
            id="entry-1",
            timestamp=datetime.now(),
            goal="Recent goal",
            workflow_used="TestWorkflow",
            result_summary="Recent result",
            tokens=100,
        )
        await memory.add_entry(entry)

        # Add summary
        summary = ShortTermSummary(
            id="sum-1",
            created_at=datetime.now(),
            summary="Summary content",
            tokens=50,
            entry_count=5,
        )
        await memory.add_short_term_summary(summary)

        # Add theme
        theme = LongTermTheme(
            id="theme-1",
            created_at=datetime.now(),
            theme="Long-term theme content",
            tokens=30,
            short_term_refs=["sum-1"],
        )
        await memory.add_long_term_theme(theme)

        context = await memory.get_context_for_llm()
        assert "Long-term context" in context
        assert "Long-term theme content" in context
        assert "Recent context (summarized)" in context
        assert "Summary content" in context
        assert "Recent interactions" in context

    async def test_get_details_for_theme(self, memory):
        """Test getting details for a theme."""
        summary = ShortTermSummary(
            id="sum-1",
            created_at=datetime.now(),
            summary="Detailed summary content",
            tokens=50,
            entry_count=5,
        )
        await memory.add_short_term_summary(summary)

        theme = LongTermTheme(
            id="theme-1",
            created_at=datetime.now(),
            theme="Theme",
            tokens=30,
            short_term_refs=["sum-1"],
        )

        details = await memory.get_details_for_theme(theme)
        assert "Detailed summary content" in details

    async def test_get_details_for_theme_no_refs(self, memory):
        """Test getting details for a theme with no valid refs."""
        theme = LongTermTheme(
            id="theme-1",
            created_at=datetime.now(),
            theme="Theme",
            tokens=30,
            short_term_refs=["nonexistent"],
        )

        details = await memory.get_details_for_theme(theme)
        assert details == "No detailed summaries available."


class TestStatistics:
    """Tests for memory statistics."""

    async def test_get_stats_empty(self, memory):
        """Test getting stats when memory is empty."""
        stats = await memory.get_stats()
        assert stats["short_term"]["entry_count"] == 0
        assert stats["short_term"]["summary_count"] == 0
        assert stats["long_term"]["theme_count"] == 0

    async def test_get_stats_with_data(self, memory):
        """Test getting stats with data."""
        # Add entry
        entry = MemoryEntry(
            id="entry-1",
            timestamp=datetime.now(),
            goal="Test goal",
            workflow_used="TestWorkflow",
            result_summary="Test result",
            tokens=100,
        )
        await memory.add_entry(entry)

        # Add summary
        summary = ShortTermSummary(
            id="sum-1",
            created_at=datetime.now(),
            summary="Summary",
            tokens=50,
            entry_count=5,
        )
        await memory.add_short_term_summary(summary)

        # Add theme
        theme = LongTermTheme(
            id="theme-1",
            created_at=datetime.now(),
            theme="Theme",
            tokens=30,
            short_term_refs=[],
        )
        await memory.add_long_term_theme(theme)

        stats = await memory.get_stats()
        assert stats["short_term"]["entry_count"] == 1
        assert stats["short_term"]["entry_tokens"] == 100
        assert stats["short_term"]["summary_count"] == 1
        assert stats["short_term"]["summary_tokens"] == 50
        assert stats["long_term"]["theme_count"] == 1
        assert stats["long_term"]["theme_tokens"] == 30


class TestEntryReplacement:
    """Tests for entry replacement behavior."""

    async def test_replace_entry_with_same_id(self, memory):
        """Test that entries with same ID are replaced."""
        entry1 = MemoryEntry(
            id="entry-1",
            timestamp=datetime.now(),
            goal="Original goal",
            workflow_used="TestWorkflow",
            result_summary="Original result",
            tokens=100,
        )
        await memory.add_entry(entry1)

        entry2 = MemoryEntry(
            id="entry-1",
            timestamp=datetime.now(),
            goal="Updated goal",
            workflow_used="TestWorkflow",
            result_summary="Updated result",
            tokens=150,
        )
        await memory.add_entry(entry2)

        entries = await memory.get_short_term_entries()
        assert len(entries) == 1
        assert entries[0].goal == "Updated goal"
        assert entries[0].tokens == 150
