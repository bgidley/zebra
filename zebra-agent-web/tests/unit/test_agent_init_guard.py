"""Agent initialisation is all-or-nothing and survives its caller going away (#231).

In prod the health check (5 s client timeout) started the agent's initialisation; after the
client gave up, the Commons publisher's thread-sensitive ORM read waited forever. The library
was already set, so every later caller skipped initialisation and used an agent with no loop
and no engine extras: web goals failed ("Agent loop not initialized") and an approved Commons
offer declined ("no publisher or library").
"""

import asyncio
import threading

import pytest
from zebra_agent_web.api import agent_engine, commons_identity


@pytest.fixture
def fresh_agent(monkeypatch):
    """An uninitialised agent module, restored afterwards."""
    for name in ("_library", "_agent_loop"):
        monkeypatch.setattr(agent_engine, name, None)
    monkeypatch.setattr(agent_engine, "_initializing", False)
    monkeypatch.setattr(agent_engine, "INIT_WAIT_SECONDS", 5)


def _slow_init(calls: list, *, fail: bool = False, delay: float = 0.2):
    """A stand-in for ``_do_init``: sets the library early and the loop late, like the real one."""

    async def _do_init():
        calls.append(threading.get_ident())
        agent_engine._library = object()
        await asyncio.sleep(delay)
        if fail:
            raise RuntimeError("boom")
        agent_engine._agent_loop = object()

    return _do_init


async def test_concurrent_callers_share_one_initialisation(fresh_agent, monkeypatch):
    calls: list = []
    monkeypatch.setattr(agent_engine, "_do_init", _slow_init(calls))

    await asyncio.gather(*(agent_engine.ensure_initialized() for _ in range(5)))

    assert len(calls) == 1
    assert agent_engine._agent_loop is not None


async def test_a_caller_mid_initialisation_waits_for_the_agent_loop(fresh_agent, monkeypatch):
    calls: list = []
    monkeypatch.setattr(agent_engine, "_do_init", _slow_init(calls, delay=0.5))

    first = asyncio.create_task(agent_engine.ensure_initialized())
    await asyncio.sleep(0.05)
    assert agent_engine._library is not None and agent_engine._agent_loop is None
    # A second caller from another thread and event loop, as async_to_sync and the
    # background goal thread do.
    seen = {}

    def other_thread():
        asyncio.run(agent_engine.ensure_initialized())
        seen["loop"] = agent_engine._agent_loop

    thread = threading.Thread(target=other_thread)
    thread.start()
    await first
    await asyncio.to_thread(thread.join, 5)

    assert seen["loop"] is not None
    assert len(calls) == 1


async def test_a_failed_initialisation_resets_and_the_next_call_retries(fresh_agent, monkeypatch):
    calls: list = []
    monkeypatch.setattr(agent_engine, "_do_init", _slow_init(calls, fail=True, delay=0))

    with pytest.raises(RuntimeError, match="boom"):
        await agent_engine.ensure_initialized()
    assert agent_engine._library is None
    assert agent_engine._initializing is False

    monkeypatch.setattr(agent_engine, "_do_init", _slow_init(calls, delay=0))
    await agent_engine.ensure_initialized()
    assert agent_engine._agent_loop is not None
    assert len(calls) == 2


async def test_waiting_gives_up_on_a_stuck_initialisation(fresh_agent, monkeypatch):
    monkeypatch.setattr(agent_engine, "INIT_WAIT_SECONDS", 0.3)
    monkeypatch.setattr(agent_engine, "_initializing", True)  # someone else, stuck
    monkeypatch.setattr(agent_engine, "_library", object())

    with pytest.raises(RuntimeError, match="did not finish"):
        await agent_engine.ensure_initialized()


@pytest.mark.parametrize("name", ["_load_state", "_owner_id", "_chain_events_sync"])
def test_commons_init_reads_are_not_thread_sensitive(name):
    """Thread-sensitive ORM calls hang once the request that started init is gone (#123)."""
    wrapped = getattr(commons_identity, name)
    assert getattr(wrapped, "_thread_sensitive", True) is False
