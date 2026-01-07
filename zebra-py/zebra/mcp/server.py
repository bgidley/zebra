"""MCP server exposing workflow capabilities as tools for Claude.

This module provides an MCP (Model Context Protocol) server that allows
Claude to create, manage, and interact with workflows.
"""

import json
import logging
from pathlib import Path
from typing import Any

from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult, TaskState
from zebra.definitions.loader import load_definition_from_yaml, validate_definition
from zebra.storage.sqlite import SQLiteStore
from zebra.tasks.registry import ActionRegistry

logger = logging.getLogger(__name__)

# Global engine instance
_engine: WorkflowEngine | None = None
_store: SQLiteStore | None = None


async def get_engine() -> WorkflowEngine:
    """Get or create the global workflow engine."""
    global _engine, _store

    if _engine is None:
        _store = SQLiteStore(Path.home() / ".zebra" / "workflows.db")
        await _store.initialize()

        registry = ActionRegistry()
        registry.register_defaults()

        _engine = WorkflowEngine(_store, registry)

    return _engine


def create_mcp_server():
    """Create and configure the MCP server.

    Returns:
        Configured MCP Server instance

    Note:
        Requires the 'mcp' package to be installed.
        Install with: pip install zebra-workflow[mcp]
    """
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import TextContent, Tool
    except ImportError:
        raise ImportError(
            "MCP package not installed. Install with: pip install zebra-workflow[mcp]"
        )

    server = Server("zebra-workflow")

    # =========================================================================
    # Tool Definitions
    # =========================================================================

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available workflow tools."""
        return [
            Tool(
                name="create_workflow",
                description="Create a new workflow from a YAML definition",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "definition_yaml": {
                            "type": "string",
                            "description": "YAML workflow definition",
                        },
                        "properties": {
                            "type": "object",
                            "description": "Initial process properties",
                        },
                    },
                    "required": ["definition_yaml"],
                },
            ),
            Tool(
                name="start_workflow",
                description="Start a created workflow",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "workflow_id": {
                            "type": "string",
                            "description": "ID of the workflow to start",
                        },
                    },
                    "required": ["workflow_id"],
                },
            ),
            Tool(
                name="get_workflow_status",
                description="Get the current status of a workflow",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "workflow_id": {
                            "type": "string",
                            "description": "ID of the workflow",
                        },
                    },
                    "required": ["workflow_id"],
                },
            ),
            Tool(
                name="list_workflows",
                description="List all active workflows",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "include_completed": {
                            "type": "boolean",
                            "description": "Include completed workflows",
                            "default": False,
                        },
                    },
                },
            ),
            Tool(
                name="get_pending_tasks",
                description="Get tasks waiting for input",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "workflow_id": {
                            "type": "string",
                            "description": "ID of the workflow",
                        },
                    },
                    "required": ["workflow_id"],
                },
            ),
            Tool(
                name="complete_task",
                description="Complete a pending task with a result",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "ID of the task to complete",
                        },
                        "result": {
                            "type": "object",
                            "description": "Result data for the task",
                        },
                    },
                    "required": ["task_id"],
                },
            ),
            Tool(
                name="pause_workflow",
                description="Pause a running workflow",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "workflow_id": {
                            "type": "string",
                            "description": "ID of the workflow to pause",
                        },
                    },
                    "required": ["workflow_id"],
                },
            ),
            Tool(
                name="resume_workflow",
                description="Resume a paused workflow",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "workflow_id": {
                            "type": "string",
                            "description": "ID of the workflow to resume",
                        },
                    },
                    "required": ["workflow_id"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool calls."""
        engine = await get_engine()

        try:
            if name == "create_workflow":
                result = await _create_workflow(engine, arguments)
            elif name == "start_workflow":
                result = await _start_workflow(engine, arguments)
            elif name == "get_workflow_status":
                result = await _get_workflow_status(engine, arguments)
            elif name == "list_workflows":
                result = await _list_workflows(engine, arguments)
            elif name == "get_pending_tasks":
                result = await _get_pending_tasks(engine, arguments)
            elif name == "complete_task":
                result = await _complete_task(engine, arguments)
            elif name == "pause_workflow":
                result = await _pause_workflow(engine, arguments)
            elif name == "resume_workflow":
                result = await _resume_workflow(engine, arguments)
            else:
                result = {"error": f"Unknown tool: {name}"}

            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        except Exception as e:
            logger.exception(f"Error calling tool {name}")
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    return server


# =============================================================================
# Tool Implementations
# =============================================================================


async def _create_workflow(engine: WorkflowEngine, args: dict) -> dict:
    """Create a workflow from YAML definition."""
    yaml_content = args["definition_yaml"]
    properties = args.get("properties", {})

    # Parse and validate definition
    definition = load_definition_from_yaml(yaml_content)
    errors = validate_definition(definition)
    if errors:
        return {"error": "Validation failed", "details": errors}

    # Create process
    process = await engine.create_process(definition, properties=properties)

    return {
        "workflow_id": process.id,
        "definition_id": definition.id,
        "definition_name": definition.name,
        "state": process.state.value,
        "message": "Workflow created. Call start_workflow to begin execution.",
    }


async def _start_workflow(engine: WorkflowEngine, args: dict) -> dict:
    """Start a workflow."""
    workflow_id = args["workflow_id"]

    process = await engine.start_process(workflow_id)
    status = await engine.get_process_status(workflow_id)

    return {
        "workflow_id": workflow_id,
        "state": process.state.value,
        "tasks": status["tasks"],
    }


async def _get_workflow_status(engine: WorkflowEngine, args: dict) -> dict:
    """Get workflow status."""
    workflow_id = args["workflow_id"]
    return await engine.get_process_status(workflow_id)


async def _list_workflows(engine: WorkflowEngine, args: dict) -> dict:
    """List workflows."""
    include_completed = args.get("include_completed", False)
    processes = await engine.store.list_processes(include_completed=include_completed)

    workflows = []
    for p in processes:
        definition = await engine.store.load_definition(p.definition_id)
        workflows.append({
            "id": p.id,
            "name": definition.name if definition else "Unknown",
            "state": p.state.value,
            "created_at": p.created_at.isoformat(),
            "updated_at": p.updated_at.isoformat(),
        })

    return {"workflows": workflows, "count": len(workflows)}


async def _get_pending_tasks(engine: WorkflowEngine, args: dict) -> dict:
    """Get pending tasks for a workflow."""
    workflow_id = args["workflow_id"]
    tasks = await engine.get_pending_tasks(workflow_id)
    definition = await engine.store.load_definition(
        (await engine.store.load_process(workflow_id)).definition_id
    )

    pending = []
    for t in tasks:
        task_def = definition.get_task(t.task_definition_id)
        pending.append({
            "id": t.id,
            "name": task_def.name,
            "prompt": t.properties.get("__prompt__"),
            "schema": t.properties.get("__schema__"),
            "options": t.properties.get("__options__"),
            "properties": {k: v for k, v in t.properties.items() if not k.startswith("__")},
        })

    return {"tasks": pending, "count": len(pending)}


async def _complete_task(engine: WorkflowEngine, args: dict) -> dict:
    """Complete a task with a result."""
    task_id = args["task_id"]
    result_data = args.get("result")

    result = TaskResult.ok(result_data) if result_data else TaskResult.ok()
    created_tasks = await engine.complete_task(task_id, result)

    return {
        "task_id": task_id,
        "completed": True,
        "created_tasks": [
            {"id": t.id, "definition": t.task_definition_id, "state": t.state.value}
            for t in created_tasks
        ],
    }


async def _pause_workflow(engine: WorkflowEngine, args: dict) -> dict:
    """Pause a workflow."""
    workflow_id = args["workflow_id"]
    process = await engine.pause_process(workflow_id)
    return {"workflow_id": workflow_id, "state": process.state.value}


async def _resume_workflow(engine: WorkflowEngine, args: dict) -> dict:
    """Resume a workflow."""
    workflow_id = args["workflow_id"]
    process = await engine.resume_process(workflow_id)
    return {"workflow_id": workflow_id, "state": process.state.value}


# =============================================================================
# CLI Entry Point
# =============================================================================


def main():
    """Run the MCP server."""
    import asyncio

    try:
        from mcp.server.stdio import stdio_server
    except ImportError:
        print("MCP package not installed. Install with: pip install zebra-workflow[mcp]")
        return

    server = create_mcp_server()

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream)

    asyncio.run(run())


if __name__ == "__main__":
    main()
