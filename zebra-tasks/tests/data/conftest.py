"""Shared helpers for data transform action tests."""

import pytest
from zebra.core.models import TaskInstance, TaskState


@pytest.fixture
def make_task():
    def _make(properties: dict) -> TaskInstance:
        return TaskInstance(
            id="task-1",
            process_id="proc-1",
            task_definition_id="transform",
            state=TaskState.RUNNING,
            foe_id="foe-1",
            properties=properties,
        )

    return _make
