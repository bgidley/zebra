"""Engine-level test: a workflow wraps an editing step in Git (#64, outcome O1).

clone → branch → file_write (stands in for an agent) → status → diff → commit → push, run by a real
WorkflowEngine against a local bare remote. This is the example documented in zebra-tasks/AGENTS.md.
"""

from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry

from vcs.helpers import sh_git
from zebra_tasks.filesystem.write import FileWriteAction
from zebra_tasks.vcs.actions import (
    GitBranchAction,
    GitCloneAction,
    GitCommitAction,
    GitDiffAction,
    GitPushAction,
    GitStatusAction,
)

WORKFLOW = """
name: "Edit Notes In Repo"
version: 1
first_task: clone
tasks:
  clone:
    name: "Clone"
    action: git_clone
    properties: {url: "{{remote_url}}", output_key: repo}
  branch:
    name: "Branch"
    action: git_branch
    properties: {repo_path: "{{repo.path}}", name: "zebra/{{topic}}", create: true}
  edit:
    name: "Edit (agent step)"
    action: file_write
    properties:
      path: "{{repo.path}}/notes/{{topic}}.md"
      content: "# {{topic}}\\n"
      allow_absolute: true
  status:
    name: "Status"
    action: git_status
    properties: {repo_path: "{{repo.path}}"}
  diff:
    name: "Diff"
    action: git_diff
    properties: {repo_path: "{{repo.path}}"}
  commit:
    name: "Commit"
    action: git_commit
    properties: {repo_path: "{{repo.path}}", message: "Add notes on {{topic}}"}
  push:
    name: "Push"
    action: git_push
    properties: {repo_path: "{{repo.path}}"}
  done:
    name: "Nothing changed"
    action: file_write
    properties: {path: "{{repo.path}}/../skipped", content: "skipped", allow_absolute: true}
routings:
  - {from: clone, to: branch}
  - {from: branch, to: edit}
  - {from: edit, to: status}
  - {from: status, to: diff}
  - {from: diff, to: commit}
  - {from: commit, to: push, condition: route_name, name: committed}
  - {from: commit, to: done, condition: route_name, name: nothing_to_commit}
"""


async def test_workflow_clones_edits_commits_and_pushes(workspace, remote, monkeypatch):
    monkeypatch.setenv("ZEBRA_GIT_AUTHOR_NAME", "Zebra")
    monkeypatch.setenv("ZEBRA_GIT_AUTHOR_EMAIL", "zebra@example.com")
    registry = ActionRegistry()
    for name, action in {
        "git_clone": GitCloneAction,
        "git_branch": GitBranchAction,
        "git_status": GitStatusAction,
        "git_diff": GitDiffAction,
        "git_commit": GitCommitAction,
        "git_push": GitPushAction,
        "file_write": FileWriteAction,
    }.items():
        registry.register_action(name, action)
    engine = WorkflowEngine(InMemoryStore(), registry)
    definition = load_definition_from_yaml(WORKFLOW)

    process = await engine.create_process(
        definition, properties={"remote_url": str(remote), "topic": "zebras"}
    )
    await engine.start_process(process.id)

    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE, process.properties
    props = process.properties
    assert props["git_status"]["files"] == [{"status": "??", "path": "notes/zebras.md"}]
    assert "+# zebras" in props["git_diff"]["diff"]
    assert props["git_commit"]["committed"] is True
    assert props["git_push"]["branch"] == "zebra/zebras"
    log = sh_git("log", "-1", "--format=%an <%ae>|%s|%H", "zebra/zebras", cwd=remote).strip()
    assert log == f"Zebra <zebra@example.com>|Add notes on zebras|{props['git_commit']['sha']}"
    assert sh_git("show", "zebra/zebras:notes/zebras.md", cwd=remote) == "# zebras\n"
