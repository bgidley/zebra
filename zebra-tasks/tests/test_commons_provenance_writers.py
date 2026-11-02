"""Every LLM writer saves through ``WorkflowLibrary.save()`` with its exposure (#229)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from zebra_agent.commons import commons_exportable
from zebra_agent.library import WorkflowLibrary
from zebra_agent.provenance import content_sha256, read_commons

from zebra_tasks.llm.base import LLMResponse, TokenUsage
from zebra_tasks.llm.client import set_llm_factory

OWNER = 1
OTHER = 2


def _workflow(prompt: str, name: str = "Project Update") -> str:
    return f"""name: "{name}"
description: "Update a project plan"
first_task: step1
tasks:
  step1:
    name: "Step"
    action: llm_call
    auto: true
    properties:
      prompt: "{prompt}"
"""


ORIGINAL = _workflow("Update the plan: {{goal}}")
MODIFIED = _workflow("Update the plan and list open risks: {{goal}}")
SECOND = _workflow("Update the plan, list open risks and owners: {{goal}}")
LEAKY = _workflow("Check Acme Corp's SLA with Jane Smith: {{goal}}")


def _response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=None,
        finish_reason="end_turn",
        usage=TokenUsage(input_tokens=10, output_tokens=20),
        model="test-model",
    )


def _provider(*contents: str) -> MagicMock:
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=[_response(c) for c in contents])
    set_llm_factory(lambda model: provider)
    return provider


@pytest.fixture
def library(tmp_path):
    lib = WorkflowLibrary(tmp_path / "workflows", owner_user_id=OWNER, sphere="home")
    lib.ensure_initialized()
    return lib


@pytest.fixture
def context(library):
    ctx = MagicMock()
    ctx.process.id = "process-1"
    ctx.process.properties = {}
    ctx.extras = {"__workflow_library__": library}
    ctx.get_process_property = MagicMock(
        side_effect=lambda k, d=None: ctx.process.properties.get(k, d)
    )
    ctx.set_process_property = MagicMock(
        side_effect=lambda k, v: ctx.process.properties.__setitem__(k, v)
    )
    ctx.resolve_template = MagicMock(side_effect=lambda x: x)
    ctx.engine.actions.format_for_prompt = MagicMock(return_value="## Actions\n- llm_call\n")
    ctx.engine.actions.has_action = MagicMock(side_effect=lambda name: name == "llm_call")
    return ctx


def _evaluation(users: list[int], run_texts: list[str] | None = None) -> dict:
    return {
        "improvement_priorities": [
            {"type": "fix", "target": "Project Update", "action": "list open risks"}
        ],
        "new_workflow_suggestions": [],
        "workflow_evaluations": [],
        "run_exposure": run_texts or ["Update the plan for next week"],
        "run_exposure_users": users,
    }


def _optimizer_task(
    library, evaluation: dict, gym_gate: bool = False, shown: list[str] | None = None
) -> MagicMock:
    task = MagicMock()
    task.properties = {
        "evaluation": evaluation,
        "existing_workflows": {
            name: library.get_workflow_yaml(name) for name in shown or ["Project Update"]
        },
        "dry_run": False,
        "gym_gate": gym_gate,
        "workflow_library_path": str(library.library_path),
    }
    return task


def _newest(library) -> dict:
    path = library._files_named("Project Update")[0]
    return read_commons(path.read_text())


async def _optimize(library, context, users, content=MODIFIED, **kwargs):
    from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

    _provider(content)
    task = _optimizer_task(library, _evaluation(users, **kwargs))
    return await WorkflowOptimizerAction().run(task, context)


class TestOptimizer:
    async def test_rewrite_records_lineage(self, library, context):
        library.add_workflow(ORIGINAL)
        result = await _optimize(library, context, [OWNER])

        assert result.success and result.output["changes_made"]
        block = _newest(library)
        assert block["content_sha256"] == content_sha256(MODIFIED)
        assert block["parent_sha256"] == content_sha256(ORIGINAL)
        assert block["ancestors"][0] == content_sha256(ORIGINAL)
        assert block["share_with"] == [] and block["origin_pubkey"] is None
        assert block["tainted_by"] == ["home"] and block["foreign_users"] is False

    async def test_another_users_runs_taint_for_good(self, library, context):
        library.add_workflow(ORIGINAL)
        await _optimize(library, context, [OWNER, OTHER])
        assert _newest(library)["foreign_users"] is True

        # A later rewrite from owner-only runs keeps the flag.
        await _optimize(library, context, [OWNER], content=SECOND)
        block = _newest(library)
        assert block["content_sha256"] == content_sha256(SECOND)
        assert block["foreign_users"] is True
        info = await library._load_workflow_info(library._files_named("Project Update")[0])
        assert commons_exportable(info) is False

    async def test_save_time_leak_rejection_is_a_failed_change(self, library, context):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        library.add_workflow(ORIGINAL)
        before = sorted(p.name for p in library.library_path.glob("*.yaml"))
        # The optimizer's own guard is skipped here (existing_workflows holds the
        # leaky text as the parent), so only save() sees the copied specifics.
        _provider(LEAKY)
        task = _optimizer_task(
            library, _evaluation([OWNER], run_texts=["Ask Jane Smith at Acme Corp about the SLA"])
        )
        task.properties["existing_workflows"] = {"Project Update": LEAKY}
        result = await WorkflowOptimizerAction().run(task, context)

        assert result.success
        assert result.output["changes_made"] == []
        assert result.output["modified_workflows"] == []
        (failed,) = result.output["failed_changes"]
        assert failed["reason"].startswith("Leak guard")
        assert sorted(p.name for p in library.library_path.glob("*.yaml")) == before

    async def test_gym_gate_stages_the_exposure(self, library, context):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        library.add_workflow(ORIGINAL)
        _provider(MODIFIED)
        task = _optimizer_task(library, _evaluation([OTHER]), gym_gate=True)
        result = await WorkflowOptimizerAction().run(task, context)

        (staged,) = result.output["pending_gym"]
        assert staged["exposure"]["user_ids"] == [OTHER]
        assert staged["exposure"]["reject"] is True


RISK_REVIEW = _workflow("Review the open risks: {{goal}}", name="Risk Review")


def _tainted(library, name: str, user: int) -> None:
    """Save workflow *name*, written from *user*'s runs."""
    from zebra_agent.provenance import Exposure

    library.save(
        _workflow("Summarise the status: {{goal}}", name=name),
        writer="optimizer",
        exposure=Exposure(user_ids=[user]),
    )


async def _create(library, context, evaluation: dict, shown: list[str]):
    """Run the optimizer's create path with *shown* workflows' YAML in the prompt."""
    from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

    provider = _provider(RISK_REVIEW)
    task = _optimizer_task(library, evaluation, shown=shown)
    result = await WorkflowOptimizerAction().run(task, context)
    assert result.success and result.output["new_workflows"], result.output
    path = library._files_named("Risk Review")[0]
    return read_commons(path.read_text()), provider


def _create_evaluation(users: list[int], **extra) -> dict:
    evaluation = {
        "improvement_priorities": [],
        "new_workflow_suggestions": [
            {"name": "Risk Review", "description": "Review open risks", "rationale": "gap"}
        ],
        "workflow_evaluations": [],
        "run_exposure": ["Update the plan for next week"],
        "run_exposure_users": users,
    }
    evaluation.update(extra)
    return evaluation


class TestShownWorkflowsTaint:
    """A writer shown another workflow carries its taint into a new lineage (#229)."""

    async def test_create_shown_a_foreign_workflow_is_foreign(self, library, context):
        _tainted(library, "Status Digest", OTHER)
        library.add_workflow(ORIGINAL)
        # Owner-only runs in the window, but the prompt shows the foreign workflow.
        block, provider = await _create(
            library, context, _create_evaluation([OWNER]), ["Status Digest", "Project Update"]
        )
        assert "Status Digest" in str(provider.complete.call_args_list[0])
        assert block["parent_sha256"] is None and block["ancestors"] == []
        assert block["foreign_users"] is True
        info = await library._load_workflow_info(library._files_named("Risk Review")[0])
        assert commons_exportable(info) is False

    async def test_create_shown_only_clean_workflows_stays_clean(self, library, context):
        _tainted(library, "Status Digest", OWNER)
        library.add_workflow(ORIGINAL)
        block, _ = await _create(
            library, context, _create_evaluation([OWNER]), ["Status Digest", "Project Update"]
        )
        assert block["foreign_users"] is False
        assert block["tainted_by"] == ["home"]

    async def test_evaluated_definitions_taint_too(self, library, context):
        # Not in the optimizer's prompt, but the evaluator judged it (definitions_shown),
        # and its findings drive what the optimizer writes.
        _tainted(library, "Status Digest", OTHER)
        library.add_workflow(ORIGINAL)
        evaluation = _create_evaluation([OWNER], definitions_shown=["Status Digest"])
        block, _ = await _create(library, context, evaluation, ["Project Update"])
        assert block["foreign_users"] is True

    async def test_priority_create_is_tainted_too(self, library, context):
        _tainted(library, "Status Digest", OTHER)
        library.add_workflow(ORIGINAL)
        evaluation = _create_evaluation([OWNER])
        evaluation["new_workflow_suggestions"] = []
        evaluation["improvement_priorities"] = [
            {"type": "create", "target": "Risk Review", "action": "review risks"}
        ]
        block, _ = await _create(library, context, evaluation, ["Status Digest"])
        assert block["foreign_users"] is True

    async def test_legacy_shown_workflow_taints(self, library, context):
        # Written before #229 (no block), perhaps by a dream cycle over other users' runs.
        legacy = _workflow("Summarise the status: {{goal}}", name="Status Digest")
        (library.library_path / "status_digest.yaml").write_text(legacy)
        library.add_workflow(ORIGINAL)
        block, _ = await _create(
            library, context, _create_evaluation([OWNER]), ["Status Digest", "Project Update"]
        )
        assert block["foreign_users"] is True
        info = next(i for i in await library.list_workflows() if i.name == "Risk Review")
        assert commons_exportable(info) is False

    def test_unreadable_shown_workflow_fails_closed(self):
        from zebra_tasks.agent.optimizer import optimizer_exposure

        broken = MagicMock()
        broken.commons_block = MagicMock(side_effect=OSError("disk"))
        exposure = optimizer_exposure(
            _create_evaluation([OWNER]), "", library=broken, shown=["Status Digest"]
        )
        assert exposure.foreign_users is True

    async def test_shown_spheres_join_tainted_by(self, library, context):
        from zebra_agent.provenance import with_commons

        library.add_workflow(ORIGINAL)
        imported = _workflow("Summarise the status: {{goal}}", name="Status Digest")
        own = library._files_named("Project Update")[0]
        block = dict(read_commons(own.read_text()))
        block.update(sphere="away", tainted_by=["away"], foreign_users=False)
        (library.library_path / "status_digest.yaml").write_text(with_commons(imported, block))
        new_block, _ = await _create(
            library, context, _create_evaluation([OWNER]), ["Status Digest", "Project Update"]
        )
        assert new_block["tainted_by"] == ["home", "away"]
        assert new_block["foreign_users"] is False


class TestSaveWorkflowFile:
    def test_delegates_to_the_library(self, library):
        from zebra_tasks.agent.optimizer import save_workflow_file

        path = save_workflow_file(str(library.library_path), "Project Update", ORIGINAL)
        block = read_commons(path.read_text())
        assert path.name == "project_update.yaml"
        assert block["content_sha256"] == content_sha256(ORIGINAL)

    def test_uses_the_given_library_for_the_owner(self, library):
        from zebra_tasks.agent.optimizer import save_workflow_file

        path = save_workflow_file(
            str(library.library_path),
            "Project Update",
            ORIGINAL,
            library=library,
            exposure={"user_ids": [OWNER]},
        )
        assert read_commons(path.read_text())["foreign_users"] is False

    def test_opens_a_library_without_one(self, library):
        from zebra_tasks.agent.optimizer import save_workflow_file

        # No owner known: any user's runs count (fail closed).
        path = save_workflow_file(
            str(library.library_path),
            "Project Update",
            ORIGINAL,
            exposure={"user_ids": [OWNER]},
        )
        assert read_commons(path.read_text())["foreign_users"] is True


class TestGym:
    async def test_promotion_saves_with_the_candidates_exposure(self, library, context):
        from zebra_tasks.agent.gym import PROMOTED, RunGoldenGymAction

        library.add_workflow(ORIGINAL)
        plan = {
            "mode": "gate",
            "promote": True,
            "candidates": [
                {
                    "name": "Project Update",
                    "modified_yaml": MODIFIED,
                    "llm_defined": True,
                    "exposure": {"user_ids": [OTHER], "reject": True},
                    "status": PROMOTED,
                    "change": {"type": "modify", "workflow": "Project Update"},
                }
            ],
            "skipped": [],
            "errors": [],
        }
        task = SimpleNamespace(
            properties={"workflow_library_path": str(library.library_path)}, id="t1"
        )
        context.extras["__metrics_store__"] = None
        await RunGoldenGymAction()._complete(task, context, plan, [])

        block = _newest(library)
        assert block["parent_sha256"] == content_sha256(ORIGINAL)
        assert block["foreign_users"] is True


class TestGoalWriters:
    async def test_creator_saves_with_the_goal_users_id(self, library, context):
        from zebra_tasks.agent.creator import WorkflowCreatorAction

        context.process.properties["__user_id__"] = OTHER
        _provider(ORIGINAL)
        task = MagicMock()
        task.properties = {"goal": "Update my project plan"}
        result = await WorkflowCreatorAction().run(task, context)

        assert result.success
        block = _newest(library)
        assert block["content_sha256"] == content_sha256(ORIGINAL)
        assert block["foreign_users"] is True

    async def test_creator_for_the_owner_is_clean(self, library, context):
        from zebra_tasks.agent.creator import WorkflowCreatorAction

        context.process.properties["__user_id__"] = OWNER
        _provider(ORIGINAL)
        task = MagicMock()
        task.properties = {"goal": "Update my project plan"}
        await WorkflowCreatorAction().run(task, context)
        assert _newest(library)["foreign_users"] is False

    async def test_variant_is_a_child_of_its_source(self, library, context):
        from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction

        library.add_workflow(ORIGINAL)
        context.process.properties["__user_id__"] = OWNER
        variant = _workflow("Weekly risks: {{goal}}", name="Project Update Weekly")
        _provider(variant)
        task = MagicMock()
        task.properties = {
            "goal": "Weekly project update",
            "source_workflow_name": "Project Update",
            "suggested_name": "Project Update Weekly",
        }
        result = await WorkflowVariantCreatorAction().run(task, context)

        assert result.success, result.error
        path = library._files_named("Project Update Weekly")[0]
        block = read_commons(path.read_text())
        assert block["parent_sha256"] == content_sha256(ORIGINAL)
        assert block["foreign_users"] is False


class TestAnalysis:
    async def test_analyzer_and_evaluator_record_run_users(self, context):
        from datetime import datetime

        from zebra_agent.metrics import WorkflowRun
        from zebra_agent.storage.metrics import InMemoryMetricsStore

        from zebra_tasks.agent.analyzer import MetricsAnalyzerAction
        from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction

        store = InMemoryMetricsStore()
        await store.initialize()
        for i, user in enumerate([OWNER, OTHER, None]):
            run = WorkflowRun.create(workflow_name="Project Update", goal=f"goal {i}")
            run.user_id = user
            run.started_at = datetime.now()
            run.success = True
            await store.record_run(run)
        context.extras["__metrics_store__"] = store

        task = MagicMock()
        task.properties = {"output_key": "metrics_analysis"}
        analysis = (await MetricsAnalyzerAction().run(task, context)).output
        assert analysis["run_user_ids"] == [OWNER, OTHER]

        _provider('{"overall_assessment": {"health_score": 80}, "improvement_priorities": []}')
        task = MagicMock()
        task.properties = {"metrics_analysis": analysis, "output_key": "evaluation"}
        result = await WorkflowEvaluatorAction().run(task, context)
        assert result.output["run_exposure_users"] == [OWNER, OTHER]
