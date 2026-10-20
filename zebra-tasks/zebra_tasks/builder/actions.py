"""Task actions that ask the host builder for a Claude Code build and publish it (#98, #172).

Both actions only write a request into the builder's spool and return; the workflow then waits on
an external task (``auto: false`` with ``external: builder``) that the daemon's builder watcher
completes when the builder answers. That keeps long builds outside the goal timeout.

Example workflow usage:
    ```yaml
    tasks:
      build:
        action: claude_code_build
        properties:
          title: "{{brief.title}}"
          prompt: "{{brief.prompt}}"
          output_key: build_job
      await_build:
        auto: false
        properties: {external: builder, job_key: build_job, wait_for: result}
    ```
"""

import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.builder.spool import get_spool

logger = logging.getLogger(__name__)

DEFAULT_REPO = "gidley/zebra"
DEFAULT_MAX_TURNS = 100
DEFAULT_MINUTES = 60
_NOT_CONFIGURED = (
    "The Claude Code builder is not configured: ZEBRA_BUILDER_SPOOL is unset or missing"
)


def _text(task: TaskInstance, context: ExecutionContext, key: str, default: str = "") -> str:
    value = task.properties.get(key, default)
    if isinstance(value, str) and "{{" in value:
        value = context.resolve_template(value)
    return str(value if value is not None else default).strip()


def _positive_int(raw: str, default: int) -> int | None:
    """Parse a template-resolved number; empty means *default*, junk or <1 means None."""
    if raw == "":
        return default
    try:
        value = int(float(raw))
    except ValueError:
        return None
    return value if value >= 1 else None


class ClaudeCodeBuildAction(TaskAction):
    """Ask the host builder to run a Claude Code build in its sandbox.

    Writes a build job (repo, base branch, prompt, test command and capability budget) and returns
    ``{job_id, ...}``. The builder validates the budget against its own ceilings and repo
    allowlist; this action never decides what is allowed.
    """

    description = (
        "Ask the host builder to run Claude Code on a repo in a sandbox (staged, not published)."
    )
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="title", type="string", description="Short name for the build", required=True
        ),
        ParameterDef(
            name="prompt",
            type="string",
            description="What Claude Code should build, with acceptance criteria",
            required=True,
        ),
        ParameterDef(
            name="repo",
            type="string",
            description="GitLab project path (must be on the builder's allowlist)",
            required=False,
            default=DEFAULT_REPO,
        ),
        ParameterDef(
            name="base_branch",
            type="string",
            description="Branch to build on",
            required=False,
            default="master",
        ),
        ParameterDef(
            name="test_command",
            type="string",
            description="Command the sandbox runs after Claude Code finishes",
            required=False,
            default="",
        ),
        ParameterDef(
            name="max_turns",
            type="number",
            description="Claude Code turn budget",
            required=False,
            default=DEFAULT_MAX_TURNS,
        ),
        ParameterDef(
            name="minutes",
            type="number",
            description="Wall-clock budget in minutes",
            required=False,
            default=DEFAULT_MINUTES,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property for the job record",
            required=False,
            default="build_job",
        ),
    ]
    outputs = [
        ParameterDef(name="job_id", type="string", description="Builder job id", required=True),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        spool = get_spool(context.extras)
        if spool is None:
            return TaskResult.fail(_NOT_CONFIGURED)

        title = _text(task, context, "title")
        prompt = _text(task, context, "prompt")
        if not title or not prompt:
            return TaskResult.fail("claude_code_build needs a title and a prompt")
        max_turns = _positive_int(_text(task, context, "max_turns"), DEFAULT_MAX_TURNS)
        minutes = _positive_int(_text(task, context, "minutes"), DEFAULT_MINUTES)
        if max_turns is None or minutes is None:
            return TaskResult.fail("max_turns and minutes must be positive whole numbers")

        job = {
            "repo": _text(task, context, "repo", DEFAULT_REPO) or DEFAULT_REPO,
            "base_branch": _text(task, context, "base_branch", "master") or "master",
            "title": title[:200],
            "prompt": prompt,
            "test_command": _text(task, context, "test_command"),
            "max_turns": max_turns,
            "minutes": minutes,
        }
        try:
            job_id = spool.submit_build(**job, process_id=context.process.id)
        except OSError as exc:
            return TaskResult.fail(f"Could not write the build job: {exc}")

        record = {"job_id": job_id, **{k: v for k, v in job.items() if k != "prompt"}}
        context.set_process_property(task.properties.get("output_key", "build_job"), record)
        logger.info("Build job %s submitted for process %s", job_id[:12], context.process.id[:12])
        return TaskResult.ok(output=record)


class PublishBuildAction(TaskAction):
    """Ask the host builder to publish an approved build as a draft merge request.

    The request names the patch by its sha256 (from the build result the reviewer saw), so the
    builder publishes exactly what was approved or nothing. Run it only on a human approval route.
    """

    description = "Publish an approved Claude Code build as a draft merge request."
    reversibility_hint = "always_irreversible"

    inputs = [
        ParameterDef(
            name="job_key",
            type="string",
            description="Process property holding the build job record",
            required=False,
            default="build_job",
        ),
        ParameterDef(
            name="result_key",
            type="string",
            description="Process property holding the build result",
            required=False,
            default="build_result",
        ),
        ParameterDef(
            name="mr_title", type="string", description="Merge request title", required=False
        ),
        ParameterDef(
            name="mr_description",
            type="string",
            description="Merge request description",
            required=False,
        ),
    ]
    outputs = [
        ParameterDef(name="job_id", type="string", description="Builder job id", required=True),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        spool = get_spool(context.extras)
        if spool is None:
            return TaskResult.fail(_NOT_CONFIGURED)

        job = context.process.properties.get(task.properties.get("job_key", "build_job")) or {}
        result = (
            context.process.properties.get(task.properties.get("result_key", "build_result")) or {}
        )
        job_id = job.get("job_id") if isinstance(job, dict) else None
        patch_sha256 = result.get("patch_sha256") if isinstance(result, dict) else None
        if not job_id or not patch_sha256 or result.get("state") != "done":
            return TaskResult.fail("There is no finished build to publish")

        try:
            spool.request_publish(
                job_id,
                patch_sha256=patch_sha256,
                mr_title=_text(task, context, "mr_title") or job.get("title", "Zebra build"),
                mr_description=_text(task, context, "mr_description"),
            )
        except (OSError, ValueError) as exc:
            return TaskResult.fail(f"Could not write the publish request: {exc}")
        logger.info("Publish requested for build job %s", job_id[:12])
        return TaskResult.ok(output={"job_id": job_id})
