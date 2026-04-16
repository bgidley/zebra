"""AssessAndRecordAction - assess effectiveness and record workflow run to memory."""

import json
import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.llm.base import Message
from zebra_tasks.llm.providers import get_provider

logger = logging.getLogger(__name__)


class AssessAndRecordAction(TaskAction):
    """
    Combine metrics recording + LLM effectiveness assessment + workflow memory write.

    This action:
    1. Records the run to the metrics store (same as old record_metrics)
    2. Uses the LLM to write a short effectiveness assessment
    3. Persists a WorkflowMemoryEntry to the memory store

    The LLM assessment is lightweight (goal + output → 2-3 sentence summary of
    what worked / didn't). It runs as a background step after execution.

    Properties:
        run_id: Unique run identifier
        workflow_name: Workflow that was executed
        goal: User's original goal
        success: Whether execution succeeded
        output: Execution output (any JSON-serialisable value)
        tokens_used: Tokens used during execution
        error: Error message if failed (optional)
        started_at: ISO timestamp when run started (optional)
        provider: LLM provider name (default: anthropic)
        model: LLM model name (optional)
        output_key: Where to store the result (default: "assess_result")

    Output:
        - recorded: bool
        - assessed: bool
        - effectiveness_notes: LLM summary

    Example workflow usage:
        ```yaml
        tasks:
          assess_and_record:
            name: "Assess and Record"
            action: assess_and_record
            auto: true
            properties:
              run_id: "{{run_id}}"
              workflow_name: "{{workflow_name}}"
              goal: "{{goal}}"
              success: "{{execution_result.success}}"
              output: "{{execution_result.output}}"
              tokens_used: "{{execution_result.tokens_used}}"
              output_key: assess_result
        ```
    """

    description = "Assess effectiveness and record workflow run to metrics and memory stores."

    inputs = [
        ParameterDef(name="run_id", type="string", description="Unique run ID", required=True),
        ParameterDef(
            name="workflow_name",
            type="string",
            description="Workflow that was executed",
            required=True,
        ),
        ParameterDef(name="goal", type="string", description="User's original goal", required=True),
        ParameterDef(
            name="success", type="bool", description="Whether run succeeded", required=True
        ),
        ParameterDef(
            name="output", type="any", description="Workflow output", required=False, default=None
        ),
        ParameterDef(
            name="tokens_used", type="int", description="Tokens used", required=False, default=0
        ),
        ParameterDef(
            name="input_tokens",
            type="int",
            description="Input tokens used",
            required=False,
            default=0,
        ),
        ParameterDef(
            name="output_tokens",
            type="int",
            description="Output tokens used",
            required=False,
            default=0,
        ),
        ParameterDef(
            name="cost",
            type="float",
            description="USD cost of execution",
            required=False,
            default=0.0,
        ),
        ParameterDef(
            name="error",
            type="string",
            description="Error message if failed",
            required=False,
            default=None,
        ),
        ParameterDef(
            name="started_at",
            type="string",
            description="ISO timestamp when run started",
            required=False,
        ),
        ParameterDef(
            name="provider",
            type="string",
            description="LLM provider name",
            required=False,
            default="anthropic",
        ),
        ParameterDef(name="model", type="string", description="LLM model name", required=False),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store result",
            required=False,
            default="assess_result",
        ),
    ]

    outputs = [
        ParameterDef(name="recorded", type="bool", description="Whether metrics were recorded"),
        ParameterDef(name="assessed", type="bool", description="Whether LLM assessment succeeded"),
        ParameterDef(
            name="effectiveness_notes",
            type="string",
            description="LLM effectiveness summary",
        ),
    ]

    ASSESSMENT_SYSTEM_PROMPT = """You are an agent that assesses workflow effectiveness.
Given a goal, the execution output, and whether it succeeded, write a 2-3 sentence summary
covering: what the workflow did well, any weaknesses or gaps, and whether this workflow
is a good fit for this type of goal in future.

Be concise and factual. Focus on actionable observations for future selection.

Respond with JSON only:
{
    "effectiveness_notes": "2-3 sentence assessment"
}"""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Execute assessment and recording."""
        # Resolve properties — use _resolve_any for fields that can be dicts/lists
        run_id = self._resolve(task, context, "run_id", "")
        workflow_name = self._resolve(task, context, "workflow_name", "")
        goal = self._resolve(task, context, "goal", "")
        success = self._resolve(task, context, "success", "false")
        output = self._resolve_any(task, context, "output")
        tokens_used = self._resolve(task, context, "tokens_used", "0")
        input_tokens = self._resolve(task, context, "input_tokens", "0")
        output_tokens = self._resolve(task, context, "output_tokens", "0")
        cost = self._resolve(task, context, "cost", "0")
        error = self._resolve(task, context, "error", "")
        started_at = self._resolve(task, context, "started_at", "")
        provider_name = task.properties.get("provider", "anthropic")
        model = task.properties.get("model")
        output_key = task.properties.get("output_key", "assess_result")

        # Resolve template vars for string fields
        if isinstance(success, str):
            success = success.lower() in ("true", "1", "yes")
        if isinstance(tokens_used, str):
            try:
                tokens_used = int(tokens_used)
            except ValueError:
                tokens_used = 0
        if isinstance(input_tokens, str):
            try:
                input_tokens = int(input_tokens)
            except ValueError:
                input_tokens = 0
        if isinstance(output_tokens, str):
            try:
                output_tokens = int(output_tokens)
            except ValueError:
                output_tokens = 0
        if isinstance(cost, str):
            try:
                cost = float(cost)
            except ValueError:
                cost = 0.0

        result = {"recorded": False, "assessed": False, "effectiveness_notes": ""}

        # ── 1. Record to metrics store ──────────────────────────────────────────
        metrics_store = context.extras.get("__metrics_store__")
        if metrics_store is not None:
            try:
                from datetime import UTC, datetime

                from zebra_agent.metrics import WorkflowRun

                run = WorkflowRun(
                    id=run_id or str(__import__("uuid").uuid4()),
                    workflow_name=workflow_name,
                    goal=goal,
                    success=success,
                    output=(
                        output[:2000]
                        if isinstance(output, str)
                        else json.dumps(output, ensure_ascii=False)[:2000]
                    )
                    if output is not None
                    else None,
                    tokens_used=int(tokens_used),
                    input_tokens=int(input_tokens),
                    output_tokens=int(output_tokens),
                    cost=float(cost),
                    error=str(error)[:500] if error else None,
                    started_at=datetime.fromisoformat(started_at)
                    if started_at and "{{" not in started_at
                    else datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                    model=context.process.properties.get("__llm_model__"),
                )
                await metrics_store.record_run(run)

                # Record task executions if available
                task_executions = context.process.properties.get("__task_executions__", [])
                if task_executions:
                    from zebra_agent.metrics import TaskExecution

                    execs = []
                    for te_dict in task_executions:
                        try:
                            te = TaskExecution(
                                id=te_dict["id"],
                                run_id=te_dict["run_id"],
                                task_definition_id=te_dict["task_definition_id"],
                                task_name=te_dict["task_name"],
                                execution_order=te_dict["execution_order"],
                                state=te_dict["state"],
                                started_at=datetime.fromisoformat(te_dict["started_at"])
                                if te_dict.get("started_at")
                                else None,
                                completed_at=datetime.fromisoformat(te_dict["completed_at"])
                                if te_dict.get("completed_at")
                                else None,
                                output=te_dict.get("output"),
                                error=te_dict.get("error"),
                            )
                            execs.append(te)
                        except Exception:
                            pass
                    if execs:
                        await metrics_store.record_task_executions(execs)

                result["recorded"] = True
                logger.info(f"AssessAndRecordAction: metrics recorded for run {run_id}")
            except Exception as e:
                logger.warning(f"AssessAndRecordAction: metrics recording failed: {e}")
        else:
            logger.info("AssessAndRecordAction: no metrics store — skipping metrics")

        # ── 2. LLM effectiveness assessment ────────────────────────────────────
        effectiveness_notes = ""
        try:
            provider = get_provider(provider_name, model)
            output_str = str(output)[:800] if output else "(no output)"
            status = "SUCCEEDED" if success else f"FAILED: {error or 'unknown error'}"

            prompt = (
                f"Goal: {goal}\n"
                f"Workflow: {workflow_name}\n"
                f"Status: {status}\n"
                f"Output summary: {output_str}\n"
                f"Tokens used: {tokens_used}"
            )

            response = await provider.complete(
                messages=[
                    Message.system(self.ASSESSMENT_SYSTEM_PROMPT),
                    Message.user(prompt),
                ],
                temperature=0.3,
                max_tokens=300,
            )

            content = response.content or "{}"
            # Strip markdown code blocks
            if "```" in content:
                import re

                match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
                if match:
                    content = match.group(1)

            data = json.loads(content)
            effectiveness_notes = data.get("effectiveness_notes", "")
            result["assessed"] = True
            logger.info(f"AssessAndRecordAction: LLM assessment complete for run {run_id}")
        except Exception as e:
            logger.warning(f"AssessAndRecordAction: LLM assessment failed: {e}")
            effectiveness_notes = f"Assessment unavailable: {e}"

        result["effectiveness_notes"] = effectiveness_notes

        # ── 3. Write WorkflowMemoryEntry ───────────────────────────────────────
        memory_store = context.extras.get("__memory_store__")
        if memory_store is not None:
            try:
                from zebra_agent.memory import WorkflowMemoryEntry

                input_summary = f"Goal: {goal[:300]}"
                output_summary = str(output)[:500] if output else "(no output)"

                entry = WorkflowMemoryEntry.create(
                    workflow_name=workflow_name,
                    goal=goal,
                    success=success,
                    input_summary=input_summary,
                    output_summary=output_summary,
                    effectiveness_notes=effectiveness_notes,
                    tokens_used=int(tokens_used),
                    run_id=run_id,
                    model=context.process.properties.get("__llm_model__", ""),
                )
                await memory_store.add_workflow_memory(entry)
                logger.info(
                    f"AssessAndRecordAction: workflow memory entry saved for {workflow_name}"
                )
            except Exception as e:
                logger.warning(f"AssessAndRecordAction: memory write failed: {e}")
        else:
            logger.info("AssessAndRecordAction: no memory store — skipping memory write")

        context.set_process_property(output_key, result)
        return TaskResult.ok(output=result)

    def _resolve(
        self, task: TaskInstance, context: ExecutionContext, key: str, default: str
    ) -> str:
        """Resolve a string property, expanding templates if needed."""
        value = task.properties.get(key, default)
        if isinstance(value, str) and "{{" in value:
            value = context.resolve_template(value)
        return value or default

    def _resolve_any(self, task: TaskInstance, context: ExecutionContext, key: str) -> object:
        """Resolve a property that may resolve to a dict, list, or primitive.

        Unlike _resolve(), this preserves the original type rather than
        stringifying — essential for the ``output`` field which is a dict.

        For a simple ``{{prop.key}}`` template it navigates the process
        property tree directly so the dict/list value is returned intact.
        """
        import re

        value = task.properties.get(key)
        if not isinstance(value, str) or "{{" not in value:
            return value

        # Try to match a single-variable template: {{a.b.c}}
        match = re.fullmatch(r"\{\{(\w+(?:\.\w+)*)\}\}", value.strip())
        if match:
            parts = match.group(1).split(".")
            obj = context.get_process_property(parts[0])
            for part in parts[1:]:
                if isinstance(obj, dict):
                    obj = obj.get(part)
                else:
                    # Can't navigate further — fall back to string resolution
                    return context.resolve_template(value)
            return obj

        # Multi-variable template — string resolution is the best we can do
        return context.resolve_template(value)
