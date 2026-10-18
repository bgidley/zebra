"""Tests for FileImprovementIssueAction — accepted requests become GitLab issues (#194)."""

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_agent.library import WorkflowLibrary

from zebra_tasks.agent.improvements import (
    REQUEST_WORKFLOW,
    FileImprovementIssueAction,
    issue_marker,
    neutralize,
    render_markdown,
)

BUILTIN = Path(__file__).parents[2] / "zebra-agent" / "workflows"
MODULE = "zebra_tasks.agent.improvements"
TOKEN = "glpat-secret-token-value"
ISSUES = "https://gitlab.com/api/v4/projects/gidley%2Fzebra/issues"
_RealAsyncClient = httpx.AsyncClient

IMPROVEMENT = {
    "title": "Add an http_fetch task action",
    "area": "task_action",
    "problem": "Workflows cannot fetch a URL.",
    "evidence": "Rejected change: unknown action 'http_fetch'",
    "suggested_change": "Add http_fetch to zebra-tasks.",
    "impact": "high",
}


class FakeGitLab:
    """Records requests; answers the issue search and create calls."""

    def __init__(self, existing=None, status_code=201, error=None):
        self.requests: list[httpx.Request] = []
        self.existing = existing or []
        self.status_code = status_code
        self.error = error

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error:
            raise self.error
        if request.method == "GET":
            return httpx.Response(200, json=self.existing)
        if self.status_code != 201:
            return httpx.Response(self.status_code, json={"message": "401 Unauthorized"})
        return httpx.Response(
            201, json={"iid": 42, "web_url": "https://gitlab.com/gidley/zebra/-/issues/42"}
        )

    def client_factory(self, **kwargs):
        return _RealAsyncClient(transport=httpx.MockTransport(self.handler), **kwargs)

    @property
    def posts(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "POST"]


@pytest.fixture(autouse=True)
def gitlab_env(monkeypatch):
    monkeypatch.setenv("ZEBRA_GITLAB_TOKEN", TOKEN)
    monkeypatch.delenv("ZEBRA_GITLAB_URL", raising=False)
    monkeypatch.delenv("ZEBRA_GITLAB_PROJECT", raising=False)


@pytest.fixture
def library(tmp_path):
    lib = WorkflowLibrary(tmp_path / "workflows")
    lib.copy_builtin_workflows(BUILTIN)
    return lib


@pytest.fixture
def engine(library):
    registry = ActionRegistry()
    registry.register_action("file_improvement_issue", FileImprovementIssueAction)
    return WorkflowEngine(InMemoryStore(), registry, extras={"__workflow_library__": library})


async def _request(engine, library, improvement=IMPROVEMENT):
    definition = library.get_workflow(REQUEST_WORKFLOW)
    process = await engine.create_process(
        definition,
        properties={
            "improvement": improvement,
            "improvement_title": improvement["title"],
            "improvement_markdown": render_markdown(improvement),
            "source_process_id": "dream-1",
        },
    )
    await engine.start_process(process.id)
    return process


async def _review(engine, process, gitlab, **verdict):
    [review] = await engine.store.load_tasks_for_process(process.id)
    with patch(f"{MODULE}.httpx.AsyncClient", gitlab.client_factory):
        await engine.complete_task(review.id, TaskResult.ok(output=verdict))
    return await engine.store.load_process(process.id)


# ---------------------------------------------------------------------------
# O1: accepted without a link → one issue, URL recorded
# ---------------------------------------------------------------------------


async def test_accepted_request_files_one_issue(engine, library):
    process = await _request(engine, library)
    gitlab = FakeGitLab()

    process = await _review(engine, process, gitlab, verdict="accepted", notes="Do it soon")

    assert process.state == ProcessState.COMPLETE
    assert process.properties["filed_issue"] == {
        "url": "https://gitlab.com/gidley/zebra/-/issues/42",
        "iid": 42,
    }
    [search, post] = gitlab.requests
    assert search.method == "GET" and str(search.url).startswith(ISSUES)
    assert search.url.params["search"] == issue_marker(process.id)
    assert str(post.url) == ISSUES
    assert post.headers["PRIVATE-TOKEN"] == TOKEN
    sent = json.loads(post.content)
    assert sent["title"] == IMPROVEMENT["title"]
    assert sent["labels"] == "dream-request"
    for text in ("Workflows cannot fetch a URL.", "#### Suggested change", "Do it soon"):
        assert text in sent["description"]
    assert "dream-1" in sent["description"]
    assert issue_marker(process.id) in sent["description"]


async def test_gitlab_url_and_project_are_configurable(engine, library, monkeypatch):
    monkeypatch.setenv("ZEBRA_GITLAB_URL", "https://git.example.com/")
    monkeypatch.setenv("ZEBRA_GITLAB_PROJECT", "team/other")
    process = await _request(engine, library)
    gitlab = FakeGitLab()

    await _review(engine, process, gitlab, verdict="accepted")

    assert str(gitlab.posts[0].url) == (
        "https://git.example.com/api/v4/projects/team%2Fother/issues"
    )


# ---------------------------------------------------------------------------
# O2: only when accepted, never twice
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verdict", ["rejected", "duplicate", "later"])
async def test_other_verdicts_make_no_call(engine, library, verdict):
    process = await _request(engine, library)
    gitlab = FakeGitLab()

    process = await _review(engine, process, gitlab, verdict=verdict)

    assert process.state == ProcessState.COMPLETE
    assert process.properties["filed_issue"] == {"skipped": "not accepted"}
    assert gitlab.requests == []


async def test_reviewer_link_is_kept_and_nothing_is_filed(engine, library):
    process = await _request(engine, library)
    gitlab = FakeGitLab()

    process = await _review(
        engine, process, gitlab, verdict="accepted", issue_url="https://gitlab.com/x/-/issues/7"
    )

    assert process.properties["filed_issue"] == {"skipped": "reviewer linked an issue"}
    assert gitlab.requests == []


async def test_rerun_after_filing_makes_no_call(engine, library):
    process = await _request(engine, library)
    await _review(engine, process, FakeGitLab(), verdict="accepted")
    process = await engine.store.load_process(process.id)

    gitlab = FakeGitLab()
    result = await _run_action(engine, process, gitlab)

    assert result.output["skipped"] == "already filed"
    assert result.output["url"] == "https://gitlab.com/gidley/zebra/-/issues/42"
    assert gitlab.requests == []


async def test_rerun_after_unsaved_post_adopts_the_existing_issue(engine, library):
    """The POST succeeded but the URL was never saved (crash): find it, don't file again."""
    process = await _request(engine, library)
    existing = [
        {
            "iid": 42,
            "web_url": "https://gitlab.com/gidley/zebra/-/issues/42",
            "description": f"...\n`{issue_marker(process.id)}`",
        }
    ]
    gitlab = FakeGitLab(existing=existing)

    process = await _review(engine, process, gitlab, verdict="accepted")

    assert process.properties["filed_issue"]["iid"] == 42
    assert gitlab.posts == []


async def test_search_hit_for_another_request_is_ignored(engine, library):
    process = await _request(engine, library)
    other = [{"iid": 9, "web_url": "u", "description": "`zebra-request:someone-else`"}]
    gitlab = FakeGitLab(existing=other)

    process = await _review(engine, process, gitlab, verdict="accepted")

    assert process.properties["filed_issue"]["iid"] == 42
    assert len(gitlab.posts) == 1


async def test_marker_must_match_exactly(engine, library):
    """A request whose id is a prefix of another's must not adopt that issue."""
    process = await _request(engine, library)
    longer = [{"iid": 9, "web_url": "u", "description": f"`{issue_marker(process.id)}0`"}]
    gitlab = FakeGitLab(existing=longer)

    process = await _review(engine, process, gitlab, verdict="accepted")

    assert process.properties["filed_issue"]["iid"] == 42
    assert len(gitlab.posts) == 1


async def test_failed_search_files_nothing(engine, library):
    class SearchDown(FakeGitLab):
        def handler(self, request):
            if request.method == "GET":
                self.requests.append(request)
                return httpx.Response(500, json={"message": "boom"})
            return super().handler(request)

    process = await _request(engine, library)
    gitlab = SearchDown()

    process = await _review(engine, process, gitlab, verdict="accepted")

    assert process.properties["filed_issue"] == {"error": "GitLab search returned 500; not filing"}
    assert gitlab.posts == []


async def test_post_timeout_then_rerun_adopts_the_created_issue(engine, library):
    """The POST timed out after GitLab created the issue: the re-run must not file again."""
    process = await _request(engine, library)
    process = await _review(
        engine, process, FakeGitLab(error=httpx.ReadTimeout("slow")), verdict="accepted"
    )
    assert "error" in process.properties["filed_issue"]

    created = [
        {
            "iid": 42,
            "web_url": "https://gitlab.com/gidley/zebra/-/issues/42",
            "description": f"body\n\n`{issue_marker(process.id)}`",
        }
    ]
    gitlab = FakeGitLab(existing=created)
    result = await _run_action(engine, process, gitlab)

    assert result.output == {"url": "https://gitlab.com/gidley/zebra/-/issues/42", "iid": 42}
    assert gitlab.posts == []


async def test_rerun_after_error_retries(engine, library, monkeypatch):
    monkeypatch.delenv("ZEBRA_GITLAB_TOKEN")
    process = await _request(engine, library)
    process = await _review(engine, process, FakeGitLab(), verdict="accepted")
    assert "error" in process.properties["filed_issue"]

    monkeypatch.setenv("ZEBRA_GITLAB_TOKEN", TOKEN)
    gitlab = FakeGitLab()
    result = await _run_action(engine, process, gitlab)

    assert result.output["iid"] == 42
    assert len(gitlab.posts) == 1


async def _run_action(engine, process, gitlab):
    from zebra.core.models import TaskInstance
    from zebra.tasks.base import ExecutionContext

    definition = await engine.store.load_definition(process.definition_id)
    context = ExecutionContext(
        engine=engine,
        store=engine.store,
        process=process,
        process_definition=definition,
        task_definition=definition.tasks["file_issue"],
        extras=engine.extras,
    )
    task = TaskInstance(
        id="t-file",
        process_id=process.id,
        task_definition_id="file_issue",
        foe_id="f",
        properties={"output_key": "filed_issue"},
    )
    with patch(f"{MODULE}.httpx.AsyncClient", gitlab.client_factory):
        return await FileImprovementIssueAction().run(task, context)


# ---------------------------------------------------------------------------
# O3: failures never break the request, never leak the token
# ---------------------------------------------------------------------------


async def test_missing_token_completes_with_error(engine, library, monkeypatch):
    monkeypatch.delenv("ZEBRA_GITLAB_TOKEN")
    process = await _request(engine, library)
    gitlab = FakeGitLab()

    process = await _review(engine, process, gitlab, verdict="accepted")

    assert process.state == ProcessState.COMPLETE
    assert process.properties["filed_issue"] == {"error": "ZEBRA_GITLAB_TOKEN is not set"}
    assert gitlab.requests == []


@pytest.mark.parametrize(
    ("gitlab", "expected"),
    [
        (FakeGitLab(error=httpx.ReadTimeout("slow")), "GitLab did not answer within 15s"),
        (FakeGitLab(error=httpx.ConnectError("down")), "network error calling GitLab"),
        (FakeGitLab(status_code=401), "GitLab returned 401"),
    ],
)
async def test_gitlab_failures_complete_with_error(engine, library, gitlab, expected):
    process = await _request(engine, library)

    process = await _review(engine, process, gitlab, verdict="accepted")

    assert process.state == ProcessState.COMPLETE
    error = process.properties["filed_issue"]["error"]
    assert expected in error
    assert TOKEN not in json.dumps(process.properties)


# ---------------------------------------------------------------------------
# O4: LLM-written text cannot run quick actions or mention people
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    ["/close", "  /assign @alice", "/label ~urgent", "/spend 1h", "\t/confidential"],
)
def test_quick_action_lines_are_escaped(line):
    out = neutralize(f"Problem text\n{line}\nmore")
    for out_line in out.split("\n"):
        assert not out_line.lstrip().startswith("/")
    assert "\\/" in out


@pytest.mark.parametrize("text", ["ping @alice", "cc @group/sub please", "@everyone"])
def test_mentions_are_broken(text):
    out = neutralize(text)
    assert "@​" in out
    for token in out.split():
        assert not (token.startswith("@") and len(token) > 1 and token[1] != "​")


def test_ordinary_text_is_unchanged():
    text = "Use path a/b and see #123 or !45.\nNo slash at start."
    assert neutralize(text) == text


async def test_injected_quick_actions_never_reach_gitlab(engine, library):
    hostile = {
        **IMPROVEMENT,
        "title": "Fix it @maintainer",
        "problem": "Broken.\n/close\n/assign @attacker\n/label ~security",
    }
    process = await _request(engine, library, hostile)
    gitlab = FakeGitLab()

    await _review(engine, process, gitlab, verdict="accepted")

    sent = json.loads(gitlab.posts[0].content)
    assert "@maintainer" not in sent["title"]
    for line in sent["description"].split("\n"):
        assert not line.lstrip().startswith("/")
    assert "@attacker" not in sent["description"]
