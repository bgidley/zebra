"""Agent task actions for workflow selection, creation, and optimization."""

from zebra_tasks.agent.analyzer import MetricsAnalyzerAction
from zebra_tasks.agent.assess_and_record import AssessAndRecordAction
from zebra_tasks.agent.consult_memory import ConsultMemoryAction
from zebra_tasks.agent.creator import WorkflowCreatorAction
from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction
from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction
from zebra_tasks.agent.optimizer import WorkflowOptimizerAction
from zebra_tasks.agent.record_metrics import RecordMetricsAction
from zebra_tasks.agent.selector import WorkflowSelectorAction
from zebra_tasks.agent.update_conceptual_memory import UpdateConceptualMemoryAction
from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction

__all__ = [
    # Core agent loop actions
    "ConsultMemoryAction",
    "WorkflowSelectorAction",
    "WorkflowCreatorAction",
    "WorkflowVariantCreatorAction",
    "ExecuteGoalWorkflowAction",
    "AssessAndRecordAction",
    "UpdateConceptualMemoryAction",
    "RecordMetricsAction",
    # Analysis and optimization actions
    "MetricsAnalyzerAction",
    "WorkflowEvaluatorAction",
    "WorkflowOptimizerAction",
]
