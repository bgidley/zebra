"""Stores must work from goal tasks that outlive the request that started them (#123).

Web goals run as background tasks that keep going after the HTTP request's
``async_to_sync`` has returned. A thread-sensitive ``sync_to_async`` call made
from such a task is routed to that request's ``CurrentThreadExecutor``, which
has already quit, and fails with "CurrentThreadExecutor already quit or is
broken". ``consult_knowledge`` swallowed that, so goals silently ran without
personal knowledge.
"""

import asyncio
import re
import threading
from pathlib import Path

import pytest
import zebra_agent_web
from asgiref.sync import async_to_sync
from zebra_agent.knowledge import KnowledgeEntry
from zebra_agent_web.knowledge_store import DjangoPersonalKnowledgeStore

pytestmark = [pytest.mark.django_db(transaction=True)]


def _run_after_request_returns(coro_factory):
    """Run a coroutine the way a web goal does: scheduled from inside a request's
    ``async_to_sync`` on a long-lived loop, and executed after that call returns."""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    started = threading.Event()
    futures = []

    async def _request():
        async def _goal():
            await asyncio.to_thread(started.wait)  # wait until the request is gone
            return await coro_factory()

        futures.append(asyncio.run_coroutine_threadsafe(_goal(), loop))

    try:
        async_to_sync(_request)()
        started.set()
        return futures[0].result(timeout=10)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)


def test_knowledge_store_usable_after_request_executor_quits():
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user(username="executor-user")
    store = DjangoPersonalKnowledgeStore()

    async def _goal_work():
        entry = KnowledgeEntry.create(
            user_id=user.id, category="facts", key="employer", value="Acme"
        )
        await store.add_entry(entry)
        return await store.get_context_for_llm(user.id)

    assert _run_after_request_returns(_goal_work) == "[facts] employer: Acme"


def test_django_stores_use_thread_insensitive_sync_to_async():
    """Guard: a bare ``@sync_to_async`` in a store reintroduces #123."""
    package = Path(zebra_agent_web.__file__).parent
    bare = re.compile(r"^\s*@sync_to_async\s*$", re.MULTILINE)
    offenders = [
        str(path.relative_to(package))
        for path in sorted(package.glob("*_store.py")) + [package / "storage.py"]
        if bare.search(path.read_text())
    ]
    assert offenders == []
