"""Fixtures for the Git task action tests: a workspace with a seeded bare remote."""

import os
from pathlib import Path

import pytest

from vcs.helpers import sh_git


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("ZEBRA_GIT_"):
            monkeypatch.delenv(key)


@pytest.fixture
def workspace(tmp_path, monkeypatch) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("ZEBRA_GIT_WORKSPACE", str(ws))
    # The tests use bare repositories in the workspace as remotes (refused by default, #241).
    monkeypatch.setenv("ZEBRA_GIT_ALLOW_LOCAL_REMOTES", "1")
    return ws


@pytest.fixture
def remote(workspace, tmp_path) -> Path:
    """A bare repository inside the workspace with one commit on master."""
    bare = workspace / "remotes" / "origin.git"
    bare.mkdir(parents=True)
    sh_git("init", "--bare", "--initial-branch=master", cwd=bare)
    seed = tmp_path / "seed"
    sh_git("clone", str(bare), str(seed), cwd=tmp_path)
    sh_git("switch", "--create", "master", cwd=seed)
    (seed / "README.md").write_text("hello\n")
    sh_git("add", "README.md", cwd=seed)
    sh_git("commit", "-m", "Initial commit", cwd=seed)
    sh_git("push", "origin", "master", cwd=seed)
    return bare


@pytest.fixture
def seed(remote, tmp_path) -> Path:
    """The working clone used to seed the remote (to move the remote on independently)."""
    return tmp_path / "seed"
