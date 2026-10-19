"""Postmortem journal triggers (#175): failed runs, timeouts / crashes and low ratings."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.agent.postmortem import WritePostmortemAction
from zebra_tasks.llm.base import LLMResponse, TokenUsage

from tests.test_ethics_workflow import (
    StubEthicsGateApprove,
    StubExecuteWorkflowFails,
    _make_registry,
)
from zebra_agent.library import WorkflowLibrary
from zebra_agent.loop import AgentLoop
from zebra_agent.metrics import WorkflowRun
from zebra_agent.postmortem import (
    needs_failure_postmortem,
    postmortem_failed_goal,
    start_postmortem,
)
from zebra_agent.storage.memory import InMemoryMemoryStore
from zebra_agent.storage.metrics import InMemoryMetricsStore

WORKFLOWS = Path(__file__).parent.parent / "workflows"

_POSTMORTEM_JSON = {
    "what_happened": "The run did not finish.",
    "root_cause": "The workflow waited on a slow search API.",
    "lesson": "When a goal needs a web search, cap it to one query.",
    "voice": "I spent the whole budget waiting on search; one query is enough.",
    "confidence": 0.6,
}


@pytest.fixture
def llm():
    """The postmortem's cheap model returns a fixed postmortem."""
    provider = MagicMock()
    provider.model = "claude-haiku-5-5"
    provider.complete = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(_POSTMORTEM_JSON),
            tool_calls=None,
            finish_reason="end_turn",
            model="claude-haiku-5-5",
            usage=TokenUsage(input_tokens=80, output_tokens=40),
        )
    )
    with patch("zebra_tasks.agent.postmortem.get_llm", return_value=provider):
        yield provider


@pytest.fixture
def main_loop():
    return load_definition_from_yaml((WORKFLOWS / "agent_main_loop.yaml").read_text())


@pytest.fixture
def library(tmp_path):
    library = WorkflowLibrary(tmp_path / "workflows")
    library.ensure_initialized()
    library.copy_builtin_workflows(WORKFLOWS)
    return library


def _postmortem_engine(memory: InMemoryMemoryStore) -> WorkflowEngine:
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("write_postmortem", WritePostmortemAction)
    return WorkflowEngine(InMemoryStore(), registry, extras={"__memory_store__": memory})


async def _failed_main_loop(engine, main_loop, **props):
    """An Agent Main Loop process that failed part-way (e.g. at the goal timeout)."""
    process = await engine.create_process(
        main_loop,
        properties={"goal": "Research solar panels", "run_id": "run-t", "__user_id__": 3, **props},
    )
    process = process.model_copy(update={"state": ProcessState.FAILED})
    await engine.store.save_process(process)
    return process


class TestMainLoopPostmortem:
    async def test_failed_run_writes_a_postmortem(self, main_loop, llm):
        memory = InMemoryMemoryStore()
        registry = _make_registry(StubEthicsGateApprove, StubExecuteWorkflowFails)
        engine = WorkflowEngine(InMemoryStore(), registry, extras={"__memory_store__": memory})
        process = await engine.create_process(
            main_loop,
            properties={
                "goal": "Write a poem",
                "run_id": "run-1",
                "available_workflows": [],
                "__help_requests__": 2,  # help budget spent: record and fail
            },
        )
        await engine.start_process(process.id)

        process = await engine.store.load_process(process.id)
        assert process.state == ProcessState.FAILED
        assert process.properties["__error__"] == "boom"
        stored = await memory.get_postmortem_by_run_id("run-1")
        assert stored.trigger == "failure"
        assert stored.lesson == _POSTMORTEM_JSON["lesson"]
        assert "Error: boom" in llm.complete.call_args.kwargs["messages"][1].content
        # The loop reflected itself, so no second (timeout) postmortem is needed
        assert not await needs_failure_postmortem(engine, process)

    async def test_successful_run_writes_none(self, main_loop, llm):
        memory = InMemoryMemoryStore()
        engine = WorkflowEngine(
            InMemoryStore(),
            _make_registry(StubEthicsGateApprove),
            extras={"__memory_store__": memory},
        )
        process = await engine.create_process(
            main_loop, properties={"goal": "Analyze data", "run_id": "run-2"}
        )
        await engine.start_process(process.id)

        assert (await engine.store.load_process(process.id)).state == ProcessState.COMPLETE
        assert await memory.get_recent_postmortems() == []
        llm.complete.assert_not_called()


class TestNeedsFailurePostmortem:
    async def test_timed_out_goal_needs_one(self, main_loop):
        engine = _postmortem_engine(InMemoryMemoryStore())
        process = await _failed_main_loop(engine, main_loop, __error__="Goal timed out after 900s")
        assert await needs_failure_postmortem(engine, process)

    async def test_kill_switch_does_not(self, main_loop):
        engine = _postmortem_engine(InMemoryMemoryStore())
        process = await _failed_main_loop(engine, main_loop, __error__="Kill switch activated")
        assert not await needs_failure_postmortem(engine, process)

    async def test_completed_goal_does_not(self, main_loop):
        engine = _postmortem_engine(InMemoryMemoryStore())
        process = await _failed_main_loop(engine, main_loop)
        process = process.model_copy(update={"state": ProcessState.COMPLETE})
        assert not await needs_failure_postmortem(engine, process)

    async def test_other_workflows_do_not(self, library):
        """A failed Postmortem (or any non-goal) process never gets a postmortem."""
        engine = _postmortem_engine(InMemoryMemoryStore())
        process = await engine.create_process(
            library.get_workflow("Postmortem"), properties={"goal": "x"}
        )
        process = process.model_copy(update={"state": ProcessState.FAILED})
        assert not await needs_failure_postmortem(engine, process)


class TestTimeoutPostmortem:
    async def test_postmortem_workflow_stores_a_timeout_lesson(self, main_loop, library, llm):
        memory = InMemoryMemoryStore()
        engine = _postmortem_engine(memory)
        process = await _failed_main_loop(
            engine,
            main_loop,
            workflow_name="Web Research",
            __error__="Goal timed out after 900s",
            __task_executions__=[{"task_name": "Search", "state": "running"}],
        )

        pid = await postmortem_failed_goal(engine, library, process)

        assert pid is not None
        assert (await engine.store.load_process(pid)).state == ProcessState.COMPLETE
        stored = await memory.get_postmortem_by_run_id("run-t")
        assert stored.trigger == "timeout"
        assert stored.workflow_name == "Web Research"
        assert stored.user_id == 3  # carried from the goal for the owner's journal
        prompt = llm.complete.call_args.kwargs["messages"][1].content
        assert "timed out or crashed" in prompt
        assert "Goal timed out after 900s" in prompt
        assert "Search [running]" in prompt

    async def test_start_failure_is_swallowed(self, tmp_path):
        engine = _postmortem_engine(InMemoryMemoryStore())
        empty = WorkflowLibrary(tmp_path / "empty")  # no Postmortem workflow
        assert await start_postmortem(engine, empty, trigger="timeout", goal="g") is None


class TestLowRatingPostmortem:
    async def _loop(self, library, memory, metrics) -> AgentLoop:
        return AgentLoop(
            library=library,
            engine=_postmortem_engine(memory),
            metrics=metrics,
            memory=memory,
        )

    async def _run(self, metrics) -> WorkflowRun:
        run = WorkflowRun.create("Creative Writing", "Write a haiku about autumn")
        run.success = True
        run.user_id = 5
        await metrics.record_run(run)
        return run

    async def test_low_rating_writes_a_postmortem(self, library, llm):
        memory, metrics = InMemoryMemoryStore(), InMemoryMetricsStore()
        run = await self._run(metrics)
        loop = await self._loop(library, memory, metrics)

        await loop.record_rating(run.id, 2)
        await asyncio.gather(*loop._background_tasks)

        stored = await memory.get_postmortem_by_run_id(run.id)
        assert stored.trigger == "low_rating"
        assert stored.user_id == 5
        assert "rated the result 2/5" in llm.complete.call_args.kwargs["messages"][1].content

    async def test_good_rating_writes_none(self, library, llm):
        memory, metrics = InMemoryMemoryStore(), InMemoryMetricsStore()
        run = await self._run(metrics)
        loop = await self._loop(library, memory, metrics)

        await loop.record_rating(run.id, 4)

        assert loop._background_tasks == set()
        assert await memory.get_recent_postmortems() == []
