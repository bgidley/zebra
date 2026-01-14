"""Zebra Tasks - Reusable task actions for the Zebra workflow engine.

This package provides commonly needed task actions including:
- Subtask execution (spawning sub-workflows)
- LLM calling (provider-agnostic LLM integration)
"""

from zebra_tasks.subtasks import (
    SubworkflowAction,
    WaitForSubworkflowAction,
    ParallelSubworkflowsAction,
)
from zebra_tasks.llm import LLMCallAction, LLMProvider

__version__ = "0.1.0"

__all__ = [
    # Subtask actions
    "SubworkflowAction",
    "WaitForSubworkflowAction",
    "ParallelSubworkflowsAction",
    # LLM actions
    "LLMCallAction",
    "LLMProvider",
]
