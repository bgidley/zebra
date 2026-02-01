"""Zebra Tasks - Reusable task actions for the Zebra workflow engine.

This package provides commonly needed task actions including:
- Subtask execution (spawning sub-workflows)
- LLM calling (provider-agnostic LLM integration)
- Human interaction (data entry and display)
- Filesystem operations (read, write, copy, move, delete, search)
"""

from zebra_tasks.filesystem import (
    DirectoryListAction,
    FileCopyAction,
    FileDeleteAction,
    FileExistsAction,
    FileInfoAction,
    FileMoveAction,
    FileReadAction,
    FileSearchAction,
    FileWriteAction,
)
from zebra_tasks.human import DataDisplayAction, DataEntryAction
from zebra_tasks.llm import LLMCallAction, LLMProvider
from zebra_tasks.subtasks import (
    ParallelSubworkflowsAction,
    SubworkflowAction,
    WaitForSubworkflowAction,
)

__version__ = "0.1.0"

__all__ = [
    # Subtask actions
    "SubworkflowAction",
    "WaitForSubworkflowAction",
    "ParallelSubworkflowsAction",
    # LLM actions
    "LLMCallAction",
    "LLMProvider",
    # Human interaction actions
    "DataEntryAction",
    "DataDisplayAction",
    # Filesystem actions
    "FileReadAction",
    "FileWriteAction",
    "FileCopyAction",
    "FileMoveAction",
    "FileDeleteAction",
    "FileSearchAction",
    "FileExistsAction",
    "FileInfoAction",
    "DirectoryListAction",
]
