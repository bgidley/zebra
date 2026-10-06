"""PropagateFailureAction turns a recorded outcome back into a task result (GitLab #140)."""

from unittest.mock import MagicMock

from zebra.core.models import TaskInstance, TaskState

from zebra_tasks.agent.propagate_failure import PropagateFailureAction


def _task(**props) -> TaskInstance:
    return TaskInstance(
        id="t1",
        process_id="p1",
        task_definition_id="report_outcome",
        state=TaskState.RUNNING,
        foe_id="f1",
        properties=props,
    )


def _context(**process_props) -> MagicMock:
    context = MagicMock()
    context.resolve_template.side_effect = lambda tpl: {
        "{{execution_result.success}}": str(process_props.get("success", "")),
        "{{execution_result.error}}": str(process_props.get("error") or ""),
    }[tpl]
    return context


async def test_unsuccessful_outcome_fails_with_error():
    result = await PropagateFailureAction().run(_task(success="False", error="boom"), MagicMock())
    assert result.success is False
    assert result.error == "boom"


async def test_successful_outcome_succeeds():
    result = await PropagateFailureAction().run(_task(success="True"), MagicMock())
    assert result.success is True


async def test_templates_resolved():
    task = _task(success="{{execution_result.success}}", error="{{execution_result.error}}")
    result = await PropagateFailureAction().run(task, _context(success=False, error="child broke"))
    assert result.success is False
    assert result.error == "child broke"


async def test_missing_error_uses_default_message():
    task = _task(success="{{execution_result.success}}", error="{{execution_result.error}}")
    result = await PropagateFailureAction().run(task, _context(success=False, error=None))
    assert result.success is False
    assert result.error == "Workflow execution failed"


async def test_bool_success_supported():
    result = await PropagateFailureAction().run(_task(success=True), MagicMock())
    assert result.success is True
