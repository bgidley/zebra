"""LLMAgentAction - an LLM task whose tools are Zebra workflows (#146).

Every tool call runs a workflow from the library as a child process of the
calling process. The task suspends (``TaskResult.suspend``) until its children
finish and the engine re-runs it with their results, so a tool call is tracked,
costed and counted like any other run, and a slow or human-in-the-loop tool
holds no coroutine. The conversation is kept in the task's properties between
turns.
"""

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef

from zebra_tasks.agent.run_kinds import SYSTEM_TAG, TOOL_GOAL_PREFIX
from zebra_tasks.agent.user_context import copy_user_properties
from zebra_tasks.llm.action import LLMCallAction
from zebra_tasks.llm.base import LLMResponse, Message, MessageRole, ToolCall, ToolDefinition
from zebra_tasks.llm.client import get_llm, model_for
from zebra_tasks.llm.structured import (
    INVALID_RETRY_NOTE,
    RAW_KEEP_CHARS,
    TRUNCATED_FINISH_REASONS,
    TRUNCATED_RETRY_NOTE,
    LLMJSONError,
    parse_llm_json,
)

logger = logging.getLogger(__name__)

#: Task property holding the conversation and pending tool calls between turns.
STATE_KEY = "__agent_state__"

#: Process property: how many llm_agent tool calls deep this process is.
DEPTH_KEY = "__agent_depth__"

#: Built-in tool that defines a new workflow, and the system workflow it runs.
DEFINE_TOOL = "define_workflow"
DEFINE_WORKFLOW_NAME = "Define Workflow"


#: Arguments of a workflow that declares no ``inputs:``.
DEFAULT_INPUTS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "goal": {
            "type": "string",
            "description": "What you want this workflow to do, in plain language",
        }
    },
    "required": ["goal"],
}

DEFINE_INPUTS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "goal": {
            "type": "string",
            "description": "What the new workflow should do, described as a reusable capability",
        },
        "suggested_name": {"type": "string", "description": "Short name for the workflow"},
    },
    "required": ["goal"],
}

# Caps on tool results: what the model sees, and what the transcript keeps.
RESULT_CHARS = 12000
TRANSCRIPT_CHARS = 500
#: Start of an unusable JSON reply quoted in the task error, for diagnosis (#216).
REPLY_PREVIEW_CHARS = 200


def tool_slug(name: str) -> str:
    """Provider-safe tool name for a workflow name ("Web Research" -> "web_research")."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return (slug or "workflow")[:64]


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return [str(v) for v in value]


def _render(value: Any, limit: int = RESULT_CHARS) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    if len(text) > limit:
        return text[:limit] + "\n...[truncated]"
    return text


def _goal_from(arguments: dict[str, Any]) -> str:
    if "goal" in arguments:
        return str(arguments["goal"])
    return "; ".join(f"{k}: {v}" for k, v in arguments.items())


def _json_container(content: str | None) -> dict | list:
    """An object or array from a JSON reply; a bare string or number is not an answer."""
    value = parse_llm_json(content)
    if not isinstance(value, dict | list):
        raise ValueError(f"expected a JSON object, got {type(value).__name__}")
    return value


def _message_to_dict(message: Message) -> dict[str, Any]:
    data: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.name:
        data["name"] = message.name
    if message.tool_call_id:
        data["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        data["tool_calls"] = [
            {"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in message.tool_calls
        ]
    return data


def _message_from_dict(data: dict[str, Any]) -> Message:
    tool_calls = data.get("tool_calls")
    return Message(
        role=MessageRole(data["role"]),
        content=data.get("content") or "",
        name=data.get("name"),
        tool_call_id=data.get("tool_call_id"),
        tool_calls=[ToolCall(**tc) for tc in tool_calls] if tool_calls else None,
    )


class LLMAgentAction(LLMCallAction):
    """
    Call an LLM that can use Zebra workflows as tools.

    Each tool is a workflow from the library. A tool call creates a child process
    of this task's process (``parent_task_id`` = this task) with the tool
    arguments as its properties, and this task suspends until the children
    finish. Their results go back to the model and the loop repeats until the
    model answers without calling a tool.

    Properties:
        prompt / system_prompt / messages: As for ``llm_call`` (resolved once)
        tools: Workflow names to offer as tools
        tool_tags: Also offer workflows with any of these tags (system workflows
            excluded), best ``success_rate`` first
        max_tag_tools: Cap on tag-selected tools (default: 8)
        allow_define_workflow: Offer ``define_workflow``, which runs the
            *Define Workflow* system workflow (ethics gate, then
            ``workflow_creator``); the new workflow is a tool from the next turn
        max_tool_turns: Model turns that may call tools before failing (default: 8)
        answer_on_budget: Instead of failing when the tool turns run out, ask once
            with no tools for an answer from what was gathered (default: false)
        max_parallel_tools: Tool calls run per turn; extra calls get an error
            result asking the model to make them next turn (default: 4)
        max_depth: Run without tools at this tool-call depth (default: 3)
        temperature, max_tokens, response_format, model: As for ``llm_call``; a
            ``json`` answer that cannot be parsed is asked for once more without
            tools, then fails the task (#216)
        output_key: Where to store the final answer (default: "agent_response")

    Declare the task ``idempotent: true`` so crash recovery re-runs an
    interrupted turn instead of flagging it for manual review.

    Example workflow usage:
        ```yaml
        tasks:
          research:
            name: "Research"
            action: llm_agent
            properties:
              idempotent: true
              prompt: "{{goal}}"
              tools: ["Web Research", "Read Web Page"]
              output_key: answer
        ```
    """

    description = (
        "Call an LLM that can use Zebra workflows as tools; each tool call runs the "
        "workflow as a child process and the task resumes with its result."
    )
    reversibility_hint = "context_dependent"

    inputs = [
        ParameterDef(
            name="prompt",
            type="string",
            description="User prompt text (supports {{var}} templates)",
            required=False,
        ),
        ParameterDef(
            name="system_prompt",
            type="string",
            description="System prompt to set LLM behavior",
            required=False,
        ),
        ParameterDef(
            name="tools",
            type="list[string]",
            description="Workflow names to offer as tools",
            required=False,
        ),
        ParameterDef(
            name="tool_tags",
            type="list[string]",
            description="Offer workflows with any of these tags, best success rate first",
            required=False,
        ),
        ParameterDef(
            name="max_tag_tools",
            type="int",
            description="Maximum number of tag-selected tools",
            required=False,
            default=8,
        ),
        ParameterDef(
            name="allow_define_workflow",
            type="bool",
            description="Let the model define and save a new workflow, then call it",
            required=False,
            default=False,
        ),
        ParameterDef(
            name="max_tool_turns",
            type="int",
            description="Model turns that may call tools before the task fails",
            required=False,
            default=8,
        ),
        ParameterDef(
            name="answer_on_budget",
            type="bool",
            description="When the tool turns run out, answer once without tools instead of failing",
            required=False,
            default=False,
        ),
        ParameterDef(
            name="max_parallel_tools",
            type="int",
            description="Tool calls run per turn; extra calls get an error result",
            required=False,
            default=4,
        ),
        ParameterDef(
            name="max_depth",
            type="int",
            description="Tool-call nesting depth at which the agent runs without tools",
            required=False,
            default=3,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the final answer",
            required=False,
            default="agent_response",
        ),
        ParameterDef(
            name="model",
            type="string",
            description="Tier (low / medium / high / max) or OpenRouter vendor/model slug",
            required=False,
        ),
    ]

    outputs = [
        ParameterDef(
            name="response",
            type="any",
            description="The model's final answer",
            required=True,
        ),
        ParameterDef(
            name="transcript",
            type="list[dict]",
            description="Tool calls: tool, workflow, arguments, process_id, success, result",
            required=True,
        ),
        ParameterDef(
            name="turns",
            type="int",
            description="Model turns that called tools",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Run one or more model turns, suspending whenever tools are called."""
        state = task.properties.get(STATE_KEY)
        if state is None:
            messages = self._build_messages(task, context)
            if not messages:
                return TaskResult.fail("No prompt or messages provided")
            state = {
                "messages": [_message_to_dict(m) for m in messages],
                "tools": await self._select_tools(task, context),
                "turns": 0,
                "pending": [],
                "transcript": [],
            }
            task.properties[STATE_KEY] = state
        elif context.subflow_results is not None and state["pending"]:
            await self._absorb_results(state, context)

        try:
            provider = get_llm(model_for(task, context), context)
        except ValueError as e:
            return TaskResult.fail(f"No LLM available: {e}")

        max_turns = int(task.properties.get("max_tool_turns", 8))
        max_parallel = int(task.properties.get("max_parallel_tools", 4))
        temperature = task.properties.get("temperature", 0.7)
        max_tokens = task.properties.get("max_tokens", 4096)

        while True:
            tools = [
                ToolDefinition(name=slug, description=t["description"], parameters=t["parameters"])
                for slug, t in state["tools"].items()
            ]
            try:
                response = await provider.complete(
                    messages=[_message_from_dict(m) for m in state["messages"]],
                    tools=tools or None,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as e:
                return TaskResult.fail(f"LLM call failed: {e}")

            if not response.tool_calls:
                return await self._finish(
                    task, context, state, response, provider, temperature, max_tokens
                )

            state["turns"] += 1
            if state["turns"] > max_turns:
                if task.properties.get("answer_on_budget"):
                    return await self._answer_without_tools(
                        task, context, state, provider, temperature, max_tokens
                    )
                return TaskResult.fail(
                    f"Stopped after {max_turns} tool turns without a final answer"
                )
            state["messages"].append(
                _message_to_dict(
                    Message.assistant(response.content or "", tool_calls=response.tool_calls)
                )
            )
            children = []
            for i, call in enumerate(response.tool_calls):
                if i >= max_parallel:
                    error = (
                        f"Too many tool calls in one turn (max {max_parallel}); "
                        "make this call next turn."
                    )
                    self._answer(state, call.id, call.name, f"Error: {error}")
                    continue
                child_id = await self._spawn(call, state, task, context)
                if child_id is not None:
                    children.append(child_id)
            if children:
                return TaskResult.suspend(children)
            # Every call was rejected (unknown tool): let the model try again.

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    async def _select_tools(
        self, task: TaskInstance, context: ExecutionContext
    ) -> dict[str, dict[str, Any]]:
        """Pick the workflows to offer, keyed by tool name."""
        library = context.extras.get("__workflow_library__")
        if library is None:
            logger.warning("llm_agent: no __workflow_library__ in context; running without tools")
            return {}
        depth = int(context.process.properties.get(DEPTH_KEY) or 0)
        max_depth = int(task.properties.get("max_depth", 3))
        if depth >= max_depth:
            logger.warning("llm_agent: tool depth %d reached limit %d; no tools", depth, max_depth)
            return {}

        infos = await library.list_workflows()
        by_name = {w.name: w for w in infos}
        own = context.process_definition.name
        chosen = []
        for name in _as_list(task.properties.get("tools")):
            if name in by_name and name != own:
                chosen.append(by_name[name])
            else:
                logger.warning("llm_agent: tool workflow %r is not available", name)

        tags = set(_as_list(task.properties.get("tool_tags")))
        if tags:
            tagged = [
                w
                for w in infos
                if tags & set(w.tags or [])
                and SYSTEM_TAG not in (w.tags or [])
                and w.name != own
                and w not in chosen
            ]
            tagged.sort(key=lambda w: (-w.success_rate, -w.use_count, w.name))
            chosen += tagged[: int(task.properties.get("max_tag_tools", 8))]

        tools: dict[str, dict[str, Any]] = {}
        for info in chosen:
            self._add_tool(tools, info)

        if _truthy(task.properties.get("allow_define_workflow")):
            try:
                library.get_workflow(DEFINE_WORKFLOW_NAME)
            except ValueError:
                logger.warning(
                    "llm_agent: %r workflow missing; no define tool", DEFINE_WORKFLOW_NAME
                )
            else:
                tools[DEFINE_TOOL] = {
                    "workflow": DEFINE_WORKFLOW_NAME,
                    "description": (
                        "Design and save a new reusable workflow when none of the other "
                        "tools fits. It is checked by the ethics gate, saved to the "
                        "library, and offered to you as a new tool on your next turn."
                    ),
                    "parameters": DEFINE_INPUTS,
                }
        return tools

    @staticmethod
    def _add_tool(tools: dict[str, dict[str, Any]], info: Any) -> str:
        """Add a workflow as a tool under a unique slug; return the slug."""
        base = slug = tool_slug(info.name)
        n = 2
        while slug in tools or slug == DEFINE_TOOL:
            slug = f"{base[:60]}_{n}"
            n += 1
        description = info.description or info.name
        if info.use_when:
            description += f" Use when: {info.use_when}"
        tools[slug] = {
            "workflow": info.name,
            "description": description,
            "parameters": info.inputs or DEFAULT_INPUTS,
        }
        return slug

    async def _spawn(
        self,
        call: ToolCall,
        state: dict[str, Any],
        task: TaskInstance,
        context: ExecutionContext,
    ) -> str | None:
        """Create the child process for a tool call, or answer it with an error."""
        tool = state["tools"].get(call.name)
        library = context.extras.get("__workflow_library__")
        error = None
        definition = None
        if tool is None:
            error = f"Unknown tool '{call.name}'. Available tools: {sorted(state['tools'])}"
        else:
            try:
                definition = library.get_workflow(tool["workflow"])
            except (AttributeError, ValueError) as e:
                error = f"Workflow '{tool['workflow']}' could not be loaded: {e}"
        arguments = call.arguments if isinstance(call.arguments, dict) else {}
        if error is not None:
            self._answer(state, call.id, call.name, f"Error: {error}")
            state["transcript"].append(
                {
                    "tool": call.name,
                    "workflow": tool["workflow"] if tool else None,
                    "arguments": arguments,
                    "process_id": None,
                    "success": False,
                    "result": error[:TRANSCRIPT_CHARS],
                }
            )
            return None

        parent = context.process.properties
        # The model never sets internal (``__``) properties on a child.
        props = {k: v for k, v in arguments.items() if not str(k).startswith("__")}
        props.setdefault("goal", _goal_from(arguments))
        if "__llm_model__" in parent:
            props["__llm_model__"] = parent["__llm_model__"]
        copy_user_properties(parent, props)
        props[DEPTH_KEY] = int(parent.get(DEPTH_KEY) or 0) + 1
        props["__parent_process_id__"] = context.process.id
        props["__parent_task_id__"] = task.id
        props["run_id"] = str(uuid.uuid4())

        child = await context.engine.create_process(
            definition,
            properties=props,
            parent_process_id=context.process.id,
            parent_task_id=task.id,
        )
        state["pending"].append(
            {
                "tool_call_id": call.id,
                "tool": call.name,
                "workflow": tool["workflow"],
                "arguments": arguments,
                "process_id": child.id,
                "run_id": props["run_id"],
                "started_at": datetime.now(UTC).isoformat(),
            }
        )
        logger.info("llm_agent: tool %s -> child process %s", call.name, child.id)
        return child.id

    async def _absorb_results(self, state: dict[str, Any], context: ExecutionContext) -> None:
        """Turn finished children into tool results, roll up cost, record metrics."""
        by_id = {r["process_id"]: r for r in context.subflow_results or []}
        for call in state["pending"]:
            result = by_id.get(call["process_id"]) or {
                "success": False,
                "output": None,
                "error": "No result for this tool call",
                "properties": {},
            }
            self._roll_up_cost(context, result.get("properties") or {})
            if not result["success"]:
                content = f"Error: the workflow failed: {result['error']}"
            elif call["tool"] == DEFINE_TOOL:
                content = await self._register_defined(state, result, context)
            else:
                content = _render(result["output"])
            self._answer(state, call["tool_call_id"], call["tool"], content)
            state["transcript"].append(
                {
                    "tool": call["tool"],
                    "workflow": call["workflow"],
                    "arguments": call["arguments"],
                    "process_id": call["process_id"],
                    "success": result["success"],
                    "result": content[:TRANSCRIPT_CHARS],
                }
            )
            await self._record_tool_run(call, result, context)
        state["pending"] = []

    async def _register_defined(
        self, state: dict[str, Any], result: dict[str, Any], context: ExecutionContext
    ) -> str:
        """Offer a workflow the define subflow just saved as a tool."""
        output = result.get("output")
        name = output.get("name") if isinstance(output, dict) else None
        library = context.extras.get("__workflow_library__")
        if not name or library is None:
            return "Error: the define workflow finished but returned no workflow name"
        info = next((w for w in await library.list_workflows() if w.name == name), None)
        if info is None:
            return f"Error: workflow '{name}' was defined but could not be loaded from the library"
        slug = self._add_tool(state["tools"], info)
        return f"Defined workflow '{name}'. It is now available as the tool '{slug}'."

    @staticmethod
    def _answer(state: dict[str, Any], tool_call_id: str, tool: str, content: str) -> None:
        state["messages"].append(_message_to_dict(Message.tool(content, tool_call_id, name=tool)))

    @staticmethod
    def _roll_up_cost(context: ExecutionContext, child_props: dict[str, Any]) -> None:
        """Add a tool child's LLM spend to this process (``__total_cost__`` etc.)."""
        cost = child_props.get("__total_cost__") or 0.0
        tokens = child_props.get("__total_tokens__") or 0
        history = child_props.get("__token_history__") or []
        if cost:
            total = context.get_process_property("__total_cost__", 0.0)
            context.set_process_property("__total_cost__", total + cost)
        if tokens:
            total = context.get_process_property("__total_tokens__", 0)
            context.set_process_property("__total_tokens__", total + tokens)
        if history:
            merged = context.get_process_property("__token_history__", []) + history
            context.set_process_property("__token_history__", merged)

    @staticmethod
    async def _record_tool_run(
        call: dict[str, Any], result: dict[str, Any], context: ExecutionContext
    ) -> None:
        """Record the tool run so the workflow's success rate and use count include it.

        Cost is recorded as 0: it is already rolled up into the calling goal, which
        records it, and counting it twice would distort the daily budget.
        """
        metrics = context.extras.get("__metrics_store__")
        if metrics is None:
            return
        try:
            from zebra_agent.metrics import WorkflowRun

            props = result.get("properties") or {}
            await metrics.record_run(
                WorkflowRun(
                    id=call["run_id"],
                    workflow_name=call["workflow"],
                    goal=f"{TOOL_GOAL_PREFIX}{_goal_from(call['arguments'])}"[:1000],
                    started_at=datetime.fromisoformat(call["started_at"]),
                    completed_at=datetime.now(UTC),
                    success=result["success"],
                    error=result.get("error"),
                    output=result.get("output"),
                    model=props.get("__llm_model__"),
                    user_id=props.get("__user_id__"),
                )
            )
        except Exception as e:
            logger.warning("llm_agent: could not record tool run %s: %s", call["run_id"], e)

    async def _answer_without_tools(
        self,
        task: TaskInstance,
        context: ExecutionContext,
        state: dict[str, Any],
        provider: Any,
        temperature: float,
        max_tokens: int,
    ) -> TaskResult:
        """Tool budget spent: ask once, with no tools, for the answer from what is known.

        The tool calls of the over-budget turn are dropped (never run or answered).
        """
        state["messages"].append(
            _message_to_dict(
                Message.user(
                    "You have used your tool budget. Answer now from what you have "
                    "gathered so far, in the format you were asked for. Do not call tools."
                )
            )
        )
        try:
            response = await provider.complete(
                messages=[_message_from_dict(m) for m in state["messages"]],
                tools=None,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            return TaskResult.fail(f"LLM call failed: {e}")
        logger.info("llm_agent: tool budget spent; answered without tools")
        return await self._finish(task, context, state, response, provider, temperature, max_tokens)

    async def _finish(
        self,
        task: TaskInstance,
        context: ExecutionContext,
        state: dict[str, Any],
        response: LLMResponse,
        provider: Any,
        temperature: float,
        max_tokens: int,
    ) -> TaskResult:
        try:
            answer = await self._final_answer(
                task, state, response, provider, temperature, max_tokens
            )
        except LLMJSONError as e:
            reply = e.failure["raw_response"][:REPLY_PREVIEW_CHARS]
            return TaskResult.fail(f"Unusable JSON answer: {e}; reply: {reply!r}")
        except Exception as e:
            return TaskResult.fail(f"LLM call failed: {e}")
        context.set_process_property(task.properties.get("output_key", "agent_response"), answer)
        task.properties.pop(STATE_KEY, None)
        return TaskResult.ok(
            output={
                "response": answer,
                "transcript": state["transcript"],
                "turns": state["turns"],
                "tools": sorted(state["tools"]),
            }
        )

    @staticmethod
    async def _final_answer(
        task: TaskInstance,
        state: dict[str, Any],
        response: LLMResponse,
        provider: Any,
        temperature: float,
        max_tokens: int,
    ) -> Any:
        """The answer to store: the reply text, or its JSON for ``response_format: json``.

        An unusable JSON reply is asked for once more, without tools, as
        ``complete_json`` does: twice ``max_tokens`` if it was cut off, else a
        JSON-only note (#216).

        Raises:
            LLMJSONError: Neither reply could be parsed.
        """
        text = response.content or ""
        if task.properties.get("response_format") != "json":
            return text
        try:
            return _json_container(text)
        except ValueError as e:
            error = str(e)
        truncated = response.finish_reason in TRUNCATED_FINISH_REASONS
        logger.warning(
            "llm_agent: unusable JSON answer (finish_reason=%s): %s; asking again",
            response.finish_reason,
            error,
        )
        note = TRUNCATED_RETRY_NOTE if truncated else INVALID_RETRY_NOTE.format(error=error)
        state["messages"].append(_message_to_dict(Message.assistant(text)))
        state["messages"].append(_message_to_dict(Message.user(note)))
        retry = await provider.complete(
            messages=[_message_from_dict(m) for m in state["messages"]],
            tools=None,
            temperature=temperature,
            max_tokens=max_tokens * 2 if truncated else max_tokens,
        )
        try:
            return _json_container(retry.content)
        except ValueError as e:
            raise LLMJSONError(
                {
                    "error": str(e),
                    "finish_reason": retry.finish_reason,
                    "truncated": retry.finish_reason in TRUNCATED_FINISH_REASONS,
                    "attempts": 2,
                    "raw_response": (retry.content or "")[:RAW_KEEP_CHARS],
                }
            ) from e
