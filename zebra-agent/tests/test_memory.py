"""Tests for the memory module."""

from datetime import datetime, timezone

import pytest

from zebra_agent.memory import (
    LongTermTheme,
    MemoryEntry,
    ShortTermSummary,
    estimate_tokens,
)


class TestMemoryEntry:
    """Tests for MemoryEntry dataclass."""

    def test_create_entry(self):
        """Test creating a memory entry."""
        entry = MemoryEntry(
            id="test-id",
            timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
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
            timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            goal="Test goal",
            workflow_used="TestWorkflow",
            result_summary="Test result",
            tokens=100,
        )
        data = entry.to_dict()
        assert data["id"] == "test-id"
        assert data["goal"] == "Test goal"
        assert data["timestamp"] == "2024-01-15T10:30:00+00:00"

    def test_from_dict(self):
        """Test creating entry from dictionary."""
        data = {
            "id": "test-id",
            "timestamp": "2024-01-15T10:30:00+00:00",
            "goal": "Test goal",
            "workflow_used": "TestWorkflow",
            "result_summary": "Test result",
            "tokens": 100,
        }
        entry = MemoryEntry.from_dict(data)
        assert entry.id == "test-id"
        assert entry.timestamp == datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        assert entry.tokens == 100


class TestShortTermSummary:
    """Tests for ShortTermSummary dataclass."""

    def test_create_summary(self):
        """Test creating a summary."""
        summary = ShortTermSummary(
            id="summary-id",
            created_at=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            summary="Summary text",
            tokens=50,
            entry_count=3,
        )
        assert summary.id == "summary-id"
        assert summary.entry_count == 3


class TestLongTermTheme:
    """Tests for LongTermTheme dataclass."""

    def test_create_theme(self):
        """Test creating a theme."""
        theme = LongTermTheme(
            id="theme-id",
            created_at=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            theme="Theme text",
            tokens=20,
            short_term_refs=["summary-1", "summary-2"],
        )
        assert theme.id == "theme-id"
        assert len(theme.short_term_refs) == 2


class TestAgentMemoryInitialization:
    """Tests for AgentMemory initialization."""

    async def test_initialization(self, memory):
        """Test that memory initializes correctly."""
        await memory._ensure_initialized()
        assert memory._initialized is True

    async def test_double_initialization(self, memory):
        """Test that double initialization is safe."""
        await memory._ensure_initialized()
        await memory._ensure_initialized()
        assert memory._initialized is True


class TestShortTermMemory:
    """Tests for short-term memory operations."""

    async def test_add_entry(self, memory):
        """Test adding an entry."""
        entry = MemoryEntry(
            id="entry-1",
            timestamp=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            goal="Goal 1",
            workflow_used="Workflow 1",
            result_summary="Result 1",
            tokens=100,
        )
        await memory.add_entry(entry)

        entries = await memory.get_short_term_entries()
        assert len(entries) == 1
        assert entries[0].id == "entry-1"

    async def test_get_short_term_entries_order(self, memory):
        """Test that entries are returned most recent first."""
        entry1 = MemoryEntry(
            id="entry-1",
            timestamp=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            goal="Goal 1",
            workflow_used="Workflow 1",
            result_summary="Result 1",
            tokens=100,
        )
        entry2 = MemoryEntry(
            id="entry-2",
            timestamp=datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc),
            goal="Goal 2",
            workflow_used="Workflow 2",
            result_summary="Result 2",
            tokens=100,
        )
        await memory.add_entry(entry1)
        await memory.add_entry(entry2)

        entries = await memory.get_short_term_entries()
        assert len(entries) == 2
        assert entries[0].id == "entry-2"  # More recent
        assert entries[1].id == "entry-1"

    async def test_get_short_term_tokens(self, memory):
        """Test calculating total tokens."""
        entry1 = MemoryEntry(
            id="entry-1",
            timestamp=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            goal="Goal 1",
            workflow_used="Workflow 1",
            result_summary="Result 1",
            tokens=100,
        )
        entry2 = MemoryEntry(
            id="entry-2",
            timestamp=datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc),
            goal="Goal 2",
            workflow_used="Workflow 2",
            result_summary="Result 2",
            tokens=200,
        )
        await memory.add_entry(entry1)
        await memory.add_entry(entry2)

        total = await memory.get_short_term_tokens()
        assert total == 300

    async def test_needs_short_term_compaction(self, memory):
        """Test compaction check."""
        # Max is 1000, threshold 0.9 -> 900
        assert await memory.needs_short_term_compaction() is False

        # Add 800 tokens (below threshold)
        entry = MemoryEntry(
            id="entry-1",
            timestamp=datetime.now(timezone.utc),
            goal="Goal",
            workflow_used="Workflow",
            result_summary="Result",
            tokens=800,
        )
        await memory.add_entry(entry)
        assert await memory.needs_short_term_compaction() is False

        # Add 150 more (total 950 > 900)
        entry2 = MemoryEntry(
            id="entry-2",
            timestamp=datetime.now(timezone.utc),
            goal="Goal",
            workflow_used="Workflow",
            result_summary="Result",
            tokens=150,
        )
        await memory.add_entry(entry2)
        assert await memory.needs_short_term_compaction() is True

    async def test_add_short_term_summary(self, memory):
        """Test adding a summary."""
        summary = ShortTermSummary(
            id="summary-1",
            created_at=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            summary="Summary text",
            tokens=50,
            entry_count=5,
        )
        await memory.add_short_term_summary(summary)

        summaries = await memory.get_short_term_summaries()
        assert len(summaries) == 1
        assert summaries[0].id == "summary-1"

    async def test_clear_short_term_entries(self, memory):
        """Test clearing entries."""
        entry = MemoryEntry(
            id="entry-1",
            timestamp=datetime.now(timezone.utc),
            goal="Goal",
            workflow_used="Workflow",
            result_summary="Result",
            tokens=100,
        )
        await memory.add_entry(entry)
        assert len(await memory.get_short_term_entries()) == 1

        await memory.clear_short_term_entries()
        assert len(await memory.get_short_term_entries()) == 0

    async def test_get_short_term_content_for_compaction(self, memory):
        """Test formatting content for compaction."""
        entry = MemoryEntry(
            id="entry-1",
            timestamp=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            goal="My Goal",
            workflow_used="My Workflow",
            result_summary="Success",
            tokens=100,
        )
        await memory.add_entry(entry)

        content = await memory.get_short_term_content_for_compaction()
        assert "My Goal" in content
        assert "My Workflow" in content
        assert "Success" in content
        assert "2024-01-15" in content


class TestLongTermMemory:
    """Tests for long-term memory operations."""

    async def test_add_long_term_theme(self, memory):
        """Test adding a theme."""
        theme = LongTermTheme(
            id="theme-1",
            created_at=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            theme="Theme text",
            tokens=20,
            short_term_refs=["summary-1"],
        )
        await memory.add_long_term_theme(theme)

        themes = await memory.get_long_term_themes()
        assert len(themes) == 1
        assert themes[0].id == "theme-1"
        assert themes[0].short_term_refs == ["summary-1"]

    async def test_get_long_term_tokens(self, memory):
        """Test calculating total theme tokens."""
        theme1 = LongTermTheme(
            id="theme-1",
            created_at=datetime.now(timezone.utc),
            theme="Theme 1",
            tokens=100,
            short_term_refs=[],
        )
        theme2 = LongTermTheme(
            id="theme-2",
            created_at=datetime.now(timezone.utc),
            theme="Theme 2",
            tokens=200,
            short_term_refs=[],
        )
        await memory.add_long_term_theme(theme1)
        await memory.add_long_term_theme(theme2)

        total = await memory.get_long_term_tokens()
        assert total == 300

    async def test_needs_long_term_compaction(self, memory):
        """Test long-term compaction check."""
        # Max 2000, threshold 0.9 -> 1800
        # Check involves sum of summaries + themes tokens

        # Add summaries: 1000 tokens
        summary = ShortTermSummary(
            id="summary-1",
            created_at=datetime.now(timezone.utc),
            summary="Summary",
            tokens=1000,
            entry_count=10,
        )
        await memory.add_short_term_summary(summary)

        # Add themes: 500 tokens
        theme = LongTermTheme(
            id="theme-1",
            created_at=datetime.now(timezone.utc),
            theme="Theme",
            tokens=500,
            short_term_refs=[],
        )
        await memory.add_long_term_theme(theme)

        # Total 1500 < 1800
        assert await memory.needs_long_term_compaction() is False

        # Add more themes: 400 tokens -> Total 1900 > 1800
        theme2 = LongTermTheme(
            id="theme-2",
            created_at=datetime.now(timezone.utc),
            theme="Theme 2",
            tokens=400,
            short_term_refs=[],
        )
        await memory.add_long_term_theme(theme2)

        assert await memory.needs_long_term_compaction() is True

    async def test_clear_short_term_summaries(self, memory):
        """Test clearing summaries."""
        summary1 = ShortTermSummary(
            id="s1",
            created_at=datetime.now(timezone.utc),
            summary="S1",
            tokens=10,
            entry_count=1,
        )
        summary2 = ShortTermSummary(
            id="s2",
            created_at=datetime.now(timezone.utc),
            summary="S2",
            tokens=10,
            entry_count=1,
        )
        await memory.add_short_term_summary(summary1)
        await memory.add_short_term_summary(summary2)

        # Clear all
        await memory.clear_short_term_summaries()
        assert len(await memory.get_short_term_summaries()) == 0

        # Add back
        await memory.add_short_term_summary(summary1)
        await memory.add_short_term_summary(summary2)

        # Clear keeping s1
        await memory.clear_short_term_summaries(keep_ids=["s1"])
        remaining = await memory.get_short_term_summaries()
        assert len(remaining) == 1
        assert remaining[0].id == "s1"


class TestCombinedContext:
    """Tests for context generation."""

    async def test_get_context_for_llm(self, memory):
        """Test generating context string."""
        # Add entry
        entry = MemoryEntry(
            id="e1",
            timestamp=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            goal="Test Goal",
            workflow_used="Test Workflow",
            result_summary="Result",
            tokens=10,
        )
        await memory.add_entry(entry)

        # Add summary
        summary = ShortTermSummary(
            id="s1",
            created_at=datetime.now(timezone.utc),
            summary="Previous summary",
            tokens=50,
            entry_count=5,
        )
        await memory.add_short_term_summary(summary)

        # Add theme
        theme = LongTermTheme(
            id="t1",
            created_at=datetime.now(timezone.utc),
            theme="Recurring pattern",
            tokens=20,
            short_term_refs=["s1"],
        )
        await memory.add_long_term_theme(theme)

        context = await memory.get_context_for_llm()

        assert "Test Goal" in context
        assert "Previous summary" in context
        assert "Recurring pattern" in context

    async def test_get_details_for_theme(self, memory):
        """Test getting details for a theme."""
        summary = ShortTermSummary(
            id="s1",
            created_at=datetime.now(timezone.utc),
            summary="Detailed summary text",
            tokens=50,
            entry_count=5,
        )
        await memory.add_short_term_summary(summary)

        theme = LongTermTheme(
            id="t1",
            created_at=datetime.now(timezone.utc),
            theme="Theme",
            tokens=20,
            short_term_refs=["s1", "non-existent"],
        )

        details = await memory.get_details_for_theme(theme)
        assert "Detailed summary text" in details


class TestEstimateTokens:
    """Test token estimation."""

    def test_estimate_tokens(self):
        text = "1234" * 10  # 40 chars
        assert estimate_tokens(text) == 10

        text = ""
        assert estimate_tokens(text) == 0
