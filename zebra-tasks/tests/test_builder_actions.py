"""claude_code_build / publish_build and the builder spool client (#98, #172)."""

import json
from types import SimpleNamespace

import pytest
from zebra.core.models import TaskInstance

from zebra_tasks.builder.actions import ClaudeCodeBuildAction, PublishBuildAction
from zebra_tasks.builder.spool import SPOOL_ENV, BuilderSpool, get_spool


class Context:
    """Just enough ExecutionContext: process properties + template resolution."""

    def __init__(self, extras: dict, properties: dict | None = None):
        self.extras = extras
        self.process = SimpleNamespace(id="proc-1", properties=dict(properties or {}))

    def resolve_template(self, value: str) -> str:
        for key, prop in self.process.properties.items():
            value = value.replace("{{" + key + "}}", str(prop))
        return value

    def set_process_property(self, key, value):
        self.process.properties[key] = value


def task(**properties) -> TaskInstance:
    return TaskInstance(
        id="t1",
        process_id="proc-1",
        task_definition_id="build",
        foe_id="f1",
        properties=properties,
    )


@pytest.fixture
def spool(tmp_path) -> BuilderSpool:
    return BuilderSpool(tmp_path)


def job_files(spool) -> list[dict]:
    return [json.loads((p / "job.json").read_text()) for p in spool.root.iterdir() if p.is_dir()]


class TestClaudeCodeBuild:
    async def test_writes_a_job_with_defaults(self, spool):
        ctx = Context({"__builder_spool__": spool}, {"what": "a hello() function"})
        result = await ClaudeCodeBuildAction().run(
            task(title="Add hello", prompt="Build {{what}}", max_turns="30"), ctx
        )
        assert result.success
        [job] = job_files(spool)
        assert job == {
            "kind": "build", "repo": "gidley/zebra", "base_branch": "master",
            "title": "Add hello", "prompt": "Build a hello() function", "test_command": "",
            "budget": {"max_turns": 30, "minutes": 60}, "process_id": "proc-1",
        }  # fmt: skip
        assert ctx.process.properties["build_job"]["job_id"] == result.output["job_id"]
        assert "prompt" not in result.output

    async def test_does_not_judge_the_budget(self, spool):
        """Ceilings are the builder's call; the action passes the request through."""
        ctx = Context({"__builder_spool__": spool})
        result = await ClaudeCodeBuildAction().run(
            task(title="t", prompt="p", max_turns=10_000, repo="someone/else"), ctx
        )
        assert result.success
        assert job_files(spool)[0]["budget"]["max_turns"] == 10_000

    @pytest.mark.parametrize("bad", ["0", "-5", "lots"])
    async def test_rejects_unusable_numbers(self, spool, bad):
        ctx = Context({"__builder_spool__": spool})
        result = await ClaudeCodeBuildAction().run(task(title="t", prompt="p", minutes=bad), ctx)
        assert not result.success
        assert job_files(spool) == []

    async def test_needs_title_and_prompt(self, spool):
        result = await ClaudeCodeBuildAction().run(
            task(title="t"), Context({"__builder_spool__": spool})
        )
        assert not result.success

    async def test_fails_clearly_without_a_spool(self, monkeypatch):
        monkeypatch.delenv(SPOOL_ENV, raising=False)
        result = await ClaudeCodeBuildAction().run(task(title="t", prompt="p"), Context({}))
        assert not result.success
        assert "ZEBRA_BUILDER_SPOOL" in result.error

    def test_reversibility(self):
        assert ClaudeCodeBuildAction.reversibility_hint == "always_reversible"
        assert PublishBuildAction.reversibility_hint == "always_irreversible"


class TestPublishBuild:
    def props(self, spool, state="done") -> dict:
        job_id = spool.submit_build(
            repo="gidley/zebra", base_branch="master", title="Add hello", prompt="p",
            test_command="", max_turns=5, minutes=5, process_id="proc-1",
        )  # fmt: skip
        return {
            "build_job": {"job_id": job_id, "title": "Add hello"},
            "__task_output_await_build": {"state": state, "patch_sha256": "ab" * 32},
        }

    async def test_requests_publish_of_the_reviewed_patch(self, spool):
        props = self.props(spool)
        ctx = Context({"__builder_spool__": spool}, props)
        result = await PublishBuildAction().run(
            task(result_key="__task_output_await_build", mr_description="d"), ctx
        )
        assert result.success
        job_id = props["build_job"]["job_id"]
        request = json.loads((spool.root / job_id / "publish.json").read_text())
        assert request == {
            "patch_sha256": "ab" * 32,
            "mr_title": "Add hello",
            "mr_description": "d",
        }

    @pytest.mark.parametrize("state", ["failed", "over_budget"])
    async def test_refuses_unfinished_builds(self, spool, state):
        ctx = Context({"__builder_spool__": spool}, self.props(spool, state))
        result = await PublishBuildAction().run(task(result_key="__task_output_await_build"), ctx)
        assert not result.success
        assert not list(spool.root.glob("*/publish.json"))


class TestSpool:
    def test_from_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv(SPOOL_ENV, str(tmp_path))
        assert BuilderSpool.from_env().root == tmp_path
        monkeypatch.setenv(SPOOL_ENV, str(tmp_path / "missing"))
        assert BuilderSpool.from_env() is None
        assert get_spool({"__builder_spool__": "injected"}) == "injected"

    def test_live_jobs(self, spool):
        def submit():
            return spool.submit_build(
                repo="r/r", base_branch="m", title="t", prompt="p", test_command="",
                max_turns=1, minutes=1, process_id="proc-1",
            )  # fmt: skip

        running, finished, cancelled, publishing, published = (submit() for _ in range(5))
        (spool.root / finished / "result.json").write_text("{}")
        spool.cancel(cancelled)
        for job_id in (publishing, published):
            (spool.root / job_id / "result.json").write_text("{}")
            spool.request_publish(job_id, patch_sha256="x", mr_title="t", mr_description="")
        (spool.root / published / "published.json").write_text("{}")

        assert sorted(spool.live_jobs()) == sorted([(running, "proc-1"), (publishing, "proc-1")])

    def test_live_jobs_empty_when_spool_dir_missing(self, tmp_path):
        missing = tmp_path / "never-created"
        assert not missing.exists()
        assert BuilderSpool(missing).live_jobs() == []

    def test_rejects_bad_job_ids(self, spool):
        with pytest.raises(ValueError):
            spool.result("../../etc")
        with pytest.raises(ValueError):
            spool.cancel("not-an-id")

    def test_reads_ignore_symlinks(self, spool, tmp_path):
        job_id = "a" * 32
        (spool.root / job_id).mkdir()
        secret = tmp_path / "secret.json"
        secret.write_text('{"password": "x"}')
        (spool.root / job_id / "result.json").symlink_to(secret)
        assert spool.result(job_id) is None
