"""DjangoStore.get_child_processes (#185): live children of a process, any user."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from zebra.core.models import ProcessInstance, ProcessState
from zebra_agent_web.storage import DjangoStore


def _process(pid: str, state: ProcessState, parent: str | None = None) -> ProcessInstance:
    now = datetime.now(UTC)
    return ProcessInstance(
        id=pid,
        definition_id="def",
        state=state,
        parent_process_id=parent,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.django_db(transaction=True)
async def test_returns_only_live_children_of_the_parent() -> None:
    store = DjangoStore()
    for process in (
        _process("parent", ProcessState.FAILED),
        _process("running", ProcessState.RUNNING, parent="parent"),
        _process("created", ProcessState.CREATED, parent="parent"),
        _process("done", ProcessState.COMPLETE, parent="parent"),
        _process("failed", ProcessState.FAILED, parent="parent"),
        _process("other", ProcessState.RUNNING, parent="someone-else"),
    ):
        await store.save_process(process)

    children = await store.get_child_processes("parent")

    assert sorted(c.id for c in children) == ["created", "running"]
