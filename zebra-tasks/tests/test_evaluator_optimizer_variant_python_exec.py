"""Functional tests for evaluator, optimizer, variant_creator, and python_exec actions.

These four modules had metadata-only or zero test coverage; this file fills the gap.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zebra_tasks.llm.base import LLMResponse, TokenUsage

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_task():
    task = MagicMock()
    task.id = "task-1"
    task.properties = {}
    return task


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.process = MagicMock()
    context.process.id = "process-1"
    context.process.properties = {}
    context.extras = {}
    context.get_process_property = MagicMock(
        side_effect=lambda k, d=None: context.process.properties.get(k, d)
    )
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    return context


def _llm_response(content: str, input_tokens: int = 10, output_tokens: int = 20) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=None,
        finish_reason="end_turn",
        usage=TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        model="test-model",
    )


def _mock_provider(content: str = "", **kwargs) -> MagicMock:
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=_llm_response(content, **kwargs))
    return provider


# ===========================================================================
# PythonExecAction
# ===========================================================================


class TestPythonExecAction:
    """Functional tests for PythonExecAction."""

    async def test_basic_result_capture(self, mock_task, mock_context):
        from zebra_tasks.compute.python_exec import PythonExecAction

        mock_task.properties = {"code": "result = 2 + 2"}
        result = await PythonExecAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.output["result"] == 4
        assert result.output["stderr"] == ""

    async def test_print_output_captured(self, mock_task, mock_context):
        from zebra_tasks.compute.python_exec import PythonExecAction

        mock_task.properties = {"code": "print('hello world')\nresult = 'done'"}
        result = await PythonExecAction().run(mock_task, mock_context)

        assert result.success is True
        assert "hello world" in result.output["stdout"]
        assert result.output["result"] == "done"

    async def test_capture_prints_false(self, mock_task, mock_context):
        from zebra_tasks.compute.python_exec import PythonExecAction

        mock_task.properties = {"code": "result = 42", "capture_prints": False}
        result = await PythonExecAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.output["result"] == 42

    async def test_result_stored_in_process_properties(self, mock_task, mock_context):
        from zebra_tasks.compute.python_exec import PythonExecAction

        mock_task.properties = {"code": "result = [1, 2, 3]", "output_key": "my_list"}
        await PythonExecAction().run(mock_task, mock_context)

        assert mock_context.process.properties["my_list"] == [1, 2, 3]

    async def test_no_result_variable_is_none(self, mock_task, mock_context):
        from zebra_tasks.compute.python_exec import PythonExecAction

        mock_task.properties = {"code": "x = 5"}
        result = await PythonExecAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.output["result"] is None

    async def test_syntax_error(self, mock_task, mock_context):
        from zebra_tasks.compute.python_exec import PythonExecAction

        mock_task.properties = {"code": "def broken("}
        result = await PythonExecAction().run(mock_task, mock_context)

        assert result.success is False
        assert "Syntax error" in result.error

    async def test_runtime_exception(self, mock_task, mock_context):
        from zebra_tasks.compute.python_exec import PythonExecAction

        mock_task.properties = {"code": "result = 1 / 0"}
        result = await PythonExecAction().run(mock_task, mock_context)

        assert result.success is False
        assert "ZeroDivisionError" in result.error

    async def test_no_code_provided(self, mock_task, mock_context):
        from zebra_tasks.compute.python_exec import PythonExecAction

        mock_task.properties = {}
        result = await PythonExecAction().run(mock_task, mock_context)

        assert result.success is False
        assert "No code provided" in result.error

    async def test_allowed_module_import(self, mock_task, mock_context):
        from zebra_tasks.compute.python_exec import PythonExecAction

        mock_task.properties = {"code": "import math\nresult = math.sqrt(16)"}
        result = await PythonExecAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.output["result"] == 4.0

    async def test_blocked_module_import(self, mock_task, mock_context):
        from zebra_tasks.compute.python_exec import PythonExecAction

        mock_task.properties = {"code": "import os\nresult = os.getcwd()"}
        result = await PythonExecAction().run(mock_task, mock_context)

        assert result.success is False
        assert "Execution error" in result.error

    async def test_props_dict_contains_process_properties(self, mock_task, mock_context):
        from zebra_tasks.compute.python_exec import PythonExecAction

        mock_context.process.properties["user_name"] = "Alice"
        mock_context.process.properties["__internal__"] = "hidden"
        mock_task.properties = {"code": "result = props.get('user_name')"}
        result = await PythonExecAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.output["result"] == "Alice"

    async def test_props_excludes_dunder_keys(self, mock_task, mock_context):
        from zebra_tasks.compute.python_exec import PythonExecAction

        mock_context.process.properties["__secret__"] = "should_be_hidden"
        mock_task.properties = {"code": "result = '__secret__' not in props"}
        result = await PythonExecAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.output["result"] is True

    async def test_template_resolved_in_code(self, mock_task, mock_context):
        from zebra_tasks.compute.python_exec import PythonExecAction

        mock_context.resolve_template = MagicMock(return_value="result = 99")
        mock_task.properties = {"code": "{{some_code}}"}
        result = await PythonExecAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.output["result"] == 99

    async def test_dict_result_serializable(self, mock_task, mock_context):
        from zebra_tasks.compute.python_exec import PythonExecAction

        mock_task.properties = {"code": "result = {'key': 'value', 'num': 42}"}
        result = await PythonExecAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.output["result"] == {"key": "value", "num": 42}

    async def test_preimported_modules_available(self, mock_task, mock_context):
        from zebra_tasks.compute.python_exec import PythonExecAction

        mock_task.properties = {"code": "result = json.dumps({'x': 1})"}
        result = await PythonExecAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.output["result"] == '{"x": 1}'


# ===========================================================================
# WorkflowEvaluatorAction
# ===========================================================================

_GOOD_EVALUATION = {
    "overall_assessment": {
        "health_score": 80,
        "summary": "System is healthy",
        "key_issues": [],
    },
    "workflow_evaluations": [
        {
            "workflow_name": "answer_question",
            "effectiveness_score": 85,
            "strengths": ["fast"],
            "weaknesses": [],
            "specific_improvements": [],
        }
    ],
    "improvement_priorities": [
        {
            "priority": 1,
            "type": "enhance",
            "target": "answer_question",
            "action": "add retry logic",
            "expected_impact": "medium",
            "rationale": "reduces errors",
        }
    ],
    "new_workflow_suggestions": [],
}


class TestWorkflowEvaluatorAction:
    """Functional tests for WorkflowEvaluatorAction."""

    async def test_no_metrics_analysis_fails(self, mock_task, mock_context):
        from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction

        mock_task.properties = {}
        result = await WorkflowEvaluatorAction().run(mock_task, mock_context)

        assert result.success is False
        assert "No metrics_analysis" in result.error

    async def test_no_provider_fails(self, mock_task, mock_context):
        from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction

        mock_task.properties = {
            "metrics_analysis": {"workflow_stats": [], "total_runs_analyzed": 0}
        }
        # No provider in properties or context
        result = await WorkflowEvaluatorAction().run(mock_task, mock_context)

        assert result.success is False
        assert "No LLM provider" in result.error

    async def test_successful_evaluation(self, mock_task, mock_context):
        from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction

        metrics = {
            "analysis_period_days": 7,
            "total_runs_analyzed": 10,
            "unique_workflows": 1,
            "workflow_stats": [
                {
                    "workflow_name": "answer_question",
                    "total_runs": 10,
                    "success_rate": 0.9,
                    "avg_rating": 4.5,
                }
            ],
            "low_performers": [],
            "failure_patterns": [],
            "recommendations": ["Looking good"],
        }
        provider = _mock_provider(json.dumps(_GOOD_EVALUATION))
        mock_context.process.properties["__llm_provider__"] = provider
        mock_task.properties = {"metrics_analysis": metrics}

        result = await WorkflowEvaluatorAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.output["overall_assessment"]["health_score"] == 80
        assert len(result.output["workflow_evaluations"]) == 1

    async def test_json_in_code_block_extracted(self, mock_task, mock_context):
        from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction

        wrapped = f"```json\n{json.dumps(_GOOD_EVALUATION)}\n```"
        provider = _mock_provider(wrapped)
        mock_context.process.properties["__llm_provider__"] = provider
        mock_task.properties = {"metrics_analysis": {"workflow_stats": []}}

        result = await WorkflowEvaluatorAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.output["overall_assessment"]["health_score"] == 80

    async def test_invalid_json_fallback(self, mock_task, mock_context):
        from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction

        provider = _mock_provider("This is not JSON at all!")
        mock_context.process.properties["__llm_provider__"] = provider
        mock_task.properties = {"metrics_analysis": {"workflow_stats": []}}

        result = await WorkflowEvaluatorAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.output["overall_assessment"]["health_score"] == 50
        assert "raw_response" in result.output

    async def test_custom_output_key(self, mock_task, mock_context):
        from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction

        provider = _mock_provider(json.dumps(_GOOD_EVALUATION))
        mock_context.process.properties["__llm_provider__"] = provider
        mock_task.properties = {
            "metrics_analysis": {"workflow_stats": []},
            "output_key": "my_eval",
        }

        result = await WorkflowEvaluatorAction().run(mock_task, mock_context)

        assert result.success is True
        assert (
            mock_context.process.properties["my_eval"]["overall_assessment"]["health_score"] == 80
        )

    async def test_token_tracking_updated(self, mock_task, mock_context):
        from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction

        mock_context.process.properties["__total_tokens__"] = 100
        provider = _mock_provider(json.dumps(_GOOD_EVALUATION), input_tokens=5, output_tokens=15)
        mock_context.process.properties["__llm_provider__"] = provider
        mock_task.properties = {"metrics_analysis": {"workflow_stats": []}}

        await WorkflowEvaluatorAction().run(mock_task, mock_context)

        assert mock_context.process.properties["__total_tokens__"] == 120

    async def test_pure_template_reference_resolved(self, mock_task, mock_context):
        """Pure {{key}} reference fetches the dict directly, not stringified."""
        from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction

        metrics_dict = {"workflow_stats": [], "total_runs_analyzed": 5}
        mock_context.process.properties["metrics_data"] = metrics_dict
        provider = _mock_provider(json.dumps(_GOOD_EVALUATION))
        mock_context.process.properties["__llm_provider__"] = provider
        mock_task.properties = {"metrics_analysis": "{{metrics_data}}"}

        result = await WorkflowEvaluatorAction().run(mock_task, mock_context)

        assert result.success is True

    async def test_build_prompt_includes_low_performers(self, mock_task, mock_context):
        from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction

        captured_messages = []

        async def capture_complete(messages, **kwargs):
            captured_messages.extend(messages)
            return _llm_response(json.dumps(_GOOD_EVALUATION))

        provider = MagicMock()
        provider.complete = capture_complete
        mock_context.process.properties["__llm_provider__"] = provider

        mock_task.properties = {
            "metrics_analysis": {
                "workflow_stats": [
                    {
                        "workflow_name": "bad_wf",
                        "total_runs": 5,
                        "success_rate": 0.4,
                        "avg_rating": None,
                    }
                ],
                "low_performers": [{"workflow_name": "bad_wf", "success_rate": 0.4}],
                "failure_patterns": [],
                "recommendations": [],
            }
        }

        await WorkflowEvaluatorAction().run(mock_task, mock_context)

        user_msg = next(m for m in captured_messages if m.role.value == "user")
        assert "bad_wf" in user_msg.content
        assert "Low-Performing" in user_msg.content


# ===========================================================================
# WorkflowOptimizerAction
# ===========================================================================

_SIMPLE_YAML = """name: New Workflow
description: A new workflow
use_when: Testing
first_task: step1
tasks:
  step1:
    name: Step 1
    action: llm_call
    auto: true
    properties:
      prompt: "{{goal}}"
"""


class TestWorkflowOptimizerAction:
    """Functional tests for WorkflowOptimizerAction."""

    async def test_no_evaluation_fails(self, mock_task, mock_context):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        mock_task.properties = {}
        result = await WorkflowOptimizerAction().run(mock_task, mock_context)

        assert result.success is False
        assert "No evaluation provided" in result.error

    async def test_no_provider_fails(self, mock_task, mock_context):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        mock_task.properties = {
            "evaluation": {"improvement_priorities": [], "new_workflow_suggestions": []}
        }
        result = await WorkflowOptimizerAction().run(mock_task, mock_context)

        assert result.success is False
        assert "No LLM provider" in result.error

    async def test_dry_run_returns_new_workflows(self, mock_task, mock_context):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        provider = _mock_provider(_SIMPLE_YAML)
        mock_context.process.properties["__llm_provider__"] = provider
        mock_task.properties = {
            "evaluation": {
                "improvement_priorities": [],
                "new_workflow_suggestions": [
                    {
                        "name": "New Workflow",
                        "description": "A new workflow",
                        "use_case": "Testing",
                        "rationale": "needed",
                    }
                ],
            },
            "dry_run": True,
        }

        result = await WorkflowOptimizerAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.output["dry_run"] is True
        assert len(result.output["new_workflows"]) == 1
        assert result.output["new_workflows"][0]["name"] == "New Workflow"

    async def test_dry_run_does_not_save_file(self, mock_task, mock_context, tmp_path):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        provider = _mock_provider(_SIMPLE_YAML)
        mock_context.process.properties["__llm_provider__"] = provider
        mock_task.properties = {
            "evaluation": {
                "improvement_priorities": [],
                "new_workflow_suggestions": [
                    {"name": "New Workflow", "description": "x", "use_case": "y", "rationale": "z"}
                ],
            },
            "dry_run": True,
            "workflow_library_path": str(tmp_path),
        }

        await WorkflowOptimizerAction().run(mock_task, mock_context)

        assert list(tmp_path.iterdir()) == []

    async def test_saves_workflow_when_not_dry_run(self, mock_task, mock_context, tmp_path):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        provider = _mock_provider(_SIMPLE_YAML)
        mock_context.process.properties["__llm_provider__"] = provider
        mock_task.properties = {
            "evaluation": {
                "improvement_priorities": [],
                "new_workflow_suggestions": [
                    {"name": "New Workflow", "description": "x", "use_case": "y", "rationale": "z"}
                ],
            },
            "dry_run": False,
            "workflow_library_path": str(tmp_path),
        }

        result = await WorkflowOptimizerAction().run(mock_task, mock_context)

        assert result.success is True
        yaml_files = list(tmp_path.glob("*.yaml"))
        assert len(yaml_files) == 1

    async def test_max_changes_limit_enforced(self, mock_task, mock_context):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        provider = _mock_provider(_SIMPLE_YAML)
        mock_context.process.properties["__llm_provider__"] = provider
        suggestions = [
            {"name": f"Workflow {i}", "description": "x", "use_case": "y", "rationale": "z"}
            for i in range(5)
        ]
        mock_task.properties = {
            "evaluation": {"improvement_priorities": [], "new_workflow_suggestions": suggestions},
            "dry_run": True,
            "max_changes": 2,
        }

        result = await WorkflowOptimizerAction().run(mock_task, mock_context)

        assert result.success is True
        assert len(result.output["changes_made"]) == 2
        assert len(result.output["skipped"]) == 3
        assert all(s["reason"] == "max_changes limit reached" for s in result.output["skipped"])

    async def test_fix_priority_modifies_existing_workflow(self, mock_task, mock_context):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        modified_yaml = _SIMPLE_YAML.replace("A new workflow", "Improved workflow")
        provider = _mock_provider(modified_yaml)
        mock_context.process.properties["__llm_provider__"] = provider
        mock_task.properties = {
            "evaluation": {
                "improvement_priorities": [
                    {
                        "priority": 1,
                        "type": "fix",
                        "target": "existing_workflow",
                        "action": "improve prompts",
                        "rationale": "low success rate",
                    }
                ],
                "new_workflow_suggestions": [],
                "workflow_evaluations": [],
            },
            "existing_workflows": {"existing_workflow": _SIMPLE_YAML},
            "dry_run": True,
        }

        result = await WorkflowOptimizerAction().run(mock_task, mock_context)

        assert result.success is True
        assert len(result.output["modified_workflows"]) == 1
        assert result.output["modified_workflows"][0]["name"] == "existing_workflow"

    async def test_fix_priority_skips_unknown_workflow(self, mock_task, mock_context):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        provider = _mock_provider(_SIMPLE_YAML)
        mock_context.process.properties["__llm_provider__"] = provider
        mock_task.properties = {
            "evaluation": {
                "improvement_priorities": [
                    {
                        "priority": 1,
                        "type": "fix",
                        "target": "nonexistent_workflow",
                        "action": "fix it",
                        "rationale": "broken",
                    }
                ],
                "new_workflow_suggestions": [],
                "workflow_evaluations": [],
            },
            "existing_workflows": {},
            "dry_run": True,
        }

        result = await WorkflowOptimizerAction().run(mock_task, mock_context)

        assert result.success is True
        assert len(result.output["skipped"]) == 1
        assert "not found" in result.output["skipped"][0]["reason"]

    async def test_custom_output_key(self, mock_task, mock_context):
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        provider = _mock_provider(_SIMPLE_YAML)
        mock_context.process.properties["__llm_provider__"] = provider
        mock_task.properties = {
            "evaluation": {"improvement_priorities": [], "new_workflow_suggestions": []},
            "dry_run": True,
            "output_key": "opt_result",
        }

        result = await WorkflowOptimizerAction().run(mock_task, mock_context)

        assert result.success is True
        assert "opt_result" in mock_context.process.properties


# ===========================================================================
# WorkflowVariantCreatorAction
# ===========================================================================

_VARIANT_YAML = """name: Code Review Strict
description: Strict code review variant
use_when: When strict code review is needed
first_task: review
tasks:
  review:
    name: Review
    action: llm_call
    auto: true
    properties:
      prompt: "{{goal}}"
      output_key: review_result
result_key: review_result
"""


class TestWorkflowVariantCreatorAction:
    """Functional tests for WorkflowVariantCreatorAction."""

    async def test_no_goal_fails(self, mock_task, mock_context):
        from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction

        mock_task.properties = {"source_workflow_name": "code_review"}
        result = await WorkflowVariantCreatorAction().run(mock_task, mock_context)

        assert result.success is False
        assert "No goal provided" in result.error

    async def test_no_source_workflow_fails(self, mock_task, mock_context):
        from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction

        mock_task.properties = {"goal": "Review my code strictly"}
        result = await WorkflowVariantCreatorAction().run(mock_task, mock_context)

        assert result.success is False
        assert "No source_workflow_name" in result.error

    async def test_no_workflow_library_fails(self, mock_task, mock_context):
        from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction

        mock_task.properties = {
            "goal": "Review my code strictly",
            "source_workflow_name": "code_review",
        }
        result = await WorkflowVariantCreatorAction().run(mock_task, mock_context)

        assert result.success is False
        assert "No workflow library" in result.error

    async def test_source_workflow_not_found_fails(self, mock_task, mock_context):
        from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction

        library = MagicMock()
        library.get_workflow_yaml = MagicMock(side_effect=ValueError("not found"))
        mock_context.extras["__workflow_library__"] = library
        mock_task.properties = {
            "goal": "Review my code strictly",
            "source_workflow_name": "missing_workflow",
        }

        result = await WorkflowVariantCreatorAction().run(mock_task, mock_context)

        assert result.success is False
        assert "Could not load source workflow" in result.error

    async def test_provider_error_fails(self, mock_task, mock_context):
        from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction

        library = MagicMock()
        library.get_workflow_yaml = MagicMock(return_value=_SIMPLE_YAML)
        mock_context.extras["__workflow_library__"] = library
        mock_task.properties = {
            "goal": "Review my code strictly",
            "source_workflow_name": "code_review",
        }

        with patch(
            "zebra_tasks.agent.variant_creator.get_provider",
            side_effect=Exception("No API key"),
        ):
            result = await WorkflowVariantCreatorAction().run(mock_task, mock_context)

        assert result.success is False
        assert "Failed to get LLM provider" in result.error

    async def test_successful_variant_creation(self, mock_task, mock_context):
        from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction

        library = MagicMock()
        library.get_workflow_yaml = MagicMock(return_value=_SIMPLE_YAML)
        library.add_workflow = MagicMock()
        mock_context.extras["__workflow_library__"] = library
        mock_task.properties = {
            "goal": "Strict code review",
            "source_workflow_name": "code_review",
            "suggested_name": "Code Review Strict",
            "reasoning": "Need stricter checks",
        }

        provider = _mock_provider(_VARIANT_YAML)
        with patch("zebra_tasks.agent.variant_creator.get_provider", return_value=provider):
            result = await WorkflowVariantCreatorAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.output["name"] == "Code Review Strict"
        assert result.output["source_workflow_name"] == "code_review"
        assert "yaml" in result.output
        assert "definition_id" in result.output

    async def test_variant_saved_to_library(self, mock_task, mock_context):
        from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction

        library = MagicMock()
        library.get_workflow_yaml = MagicMock(return_value=_SIMPLE_YAML)
        library.add_workflow = MagicMock()
        mock_context.extras["__workflow_library__"] = library
        mock_task.properties = {
            "goal": "Strict code review",
            "source_workflow_name": "code_review",
        }

        provider = _mock_provider(_VARIANT_YAML)
        with patch("zebra_tasks.agent.variant_creator.get_provider", return_value=provider):
            result = await WorkflowVariantCreatorAction().run(mock_task, mock_context)

        assert result.success is True
        library.add_workflow.assert_called_once()

    async def test_invalid_yaml_from_llm_fails(self, mock_task, mock_context):
        from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction

        library = MagicMock()
        library.get_workflow_yaml = MagicMock(return_value=_SIMPLE_YAML)
        mock_context.extras["__workflow_library__"] = library
        mock_task.properties = {
            "goal": "Strict code review",
            "source_workflow_name": "code_review",
        }

        provider = _mock_provider("this is: not: valid: yaml: {{{{")
        with patch("zebra_tasks.agent.variant_creator.get_provider", return_value=provider):
            result = await WorkflowVariantCreatorAction().run(mock_task, mock_context)

        assert result.success is False
        assert "invalid variant YAML" in result.error

    async def test_custom_output_key_stored(self, mock_task, mock_context):
        from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction

        library = MagicMock()
        library.get_workflow_yaml = MagicMock(return_value=_SIMPLE_YAML)
        library.add_workflow = MagicMock()
        mock_context.extras["__workflow_library__"] = library
        mock_task.properties = {
            "goal": "Strict code review",
            "source_workflow_name": "code_review",
            "output_key": "my_variant",
        }

        provider = _mock_provider(_VARIANT_YAML)
        with patch("zebra_tasks.agent.variant_creator.get_provider", return_value=provider):
            result = await WorkflowVariantCreatorAction().run(mock_task, mock_context)

        assert result.success is True
        assert "my_variant" in mock_context.process.properties

    async def test_progress_callback_invoked(self, mock_task, mock_context):
        from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction

        library = MagicMock()
        library.get_workflow_yaml = MagicMock(return_value=_SIMPLE_YAML)
        library.add_workflow = MagicMock()
        mock_context.extras["__workflow_library__"] = library

        progress_events = []

        async def capture_progress(event, data):
            progress_events.append((event, data))

        mock_context.extras["__progress_callback__"] = capture_progress
        mock_task.properties = {
            "goal": "Strict code review",
            "source_workflow_name": "code_review",
        }

        provider = _mock_provider(_VARIANT_YAML)
        with patch("zebra_tasks.agent.variant_creator.get_provider", return_value=provider):
            await WorkflowVariantCreatorAction().run(mock_task, mock_context)

        event_names = [e[0] for e in progress_events]
        assert "creating_variant" in event_names
        assert "workflow_selected" in event_names

    async def test_markdown_yaml_block_stripped(self, mock_task, mock_context):
        """LLM sometimes wraps output in ```yaml ... ``` blocks — verify extraction."""
        from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction

        library = MagicMock()
        library.get_workflow_yaml = MagicMock(return_value=_SIMPLE_YAML)
        library.add_workflow = MagicMock()
        mock_context.extras["__workflow_library__"] = library
        mock_task.properties = {
            "goal": "Strict code review",
            "source_workflow_name": "code_review",
        }

        wrapped = f"```yaml\n{_VARIANT_YAML}\n```"
        provider = _mock_provider(wrapped)
        with patch("zebra_tasks.agent.variant_creator.get_provider", return_value=provider):
            result = await WorkflowVariantCreatorAction().run(mock_task, mock_context)

        assert result.success is True
        assert result.output["name"] == "Code Review Strict"
