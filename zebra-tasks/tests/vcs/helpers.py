"""Helpers for the Git task action tests."""

import os
import subprocess
from pathlib import Path

from zebra.core.models import TaskInstance, TaskState

SEED_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Seed",
    "GIT_AUTHOR_EMAIL": "seed@example.com",
    "GIT_COMMITTER_NAME": "Seed",
    "GIT_COMMITTER_EMAIL": "seed@example.com",
}


def sh_git(*args: str, cwd: Path) -> str:
    """Run git for test setup/inspection (not through the actions)."""
    env = {**os.environ, **SEED_ENV}
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True
    ).stdout


def make_task(properties: dict) -> TaskInstance:
    return TaskInstance(
        id="task-1",
        process_id="test_process",
        task_definition_id="git_step",
        state=TaskState.RUNNING,
        foe_id="foe-1",
        properties=properties,
    )
