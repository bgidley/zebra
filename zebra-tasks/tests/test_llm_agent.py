"""llm_agent: workflows as LLM tools, each call a suspended-on subflow (#146)."""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import (
    ProcessDefinition,
    ProcessState,
    TaskDefinition,
    TaskInstance,
    TaskResult,
    TaskState,
)
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_agent.library import LLM_DEFINED_TAG, WorkflowInfo, WorkflowLibrary
from zebra_agent.storage.metrics import InMemoryMetricsStore

from zebra_tasks.llm.agent import (
    DEFAULT_INPUTS,
    DEFINE_TOOL,
    DEPTH_KEY,
    STATE_KEY,
    LLMAgentAction,
    tool_slug,
)
from zebra_tasks.llm.base import (
    LLMProvider,
    LLMResponse,
    Message,
    MessageRole,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)
from zebra_tasks.llm.client import set_llm_factory

# ---------------------------------------------------------------------------
# Scripted provider
# ---------------------------------------------------------------------------


@dataclass
class Call:
    messages: list[Message]
    tools: list[ToolDefinition] | None


Step = Callable[[Call], LLMResponse]


def say(text: str) -> Step:
    return lambda call: LLMResponse(
        content=text,
        tool_calls=None,
        finish_reason="end_turn",
        usage=TokenUsage(100, 50, cost_usd=0.001),
        model="claude-haiku-5-5",
    )


def use(*calls: tuple[str, dict]) -> Step:
    return lambda call: LLMResponse(
        content="",
        tool_calls=[
            ToolCall(id=f"call_{name}_{i}", name=name, arguments=args)
            for i, (name, args) in enumerate(calls)
        ],
        finish_reason="tool_use",
        usage=TokenUsage(100, 20, cost_usd=0.001),
        model="claude-haiku-5-5",
    )


@dataclass
class ScriptedProvider(LLMProvider):
    script: list[Step] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)

    async def complete(self, messages, tools=None, temperature=0.7, max_tokens=4096, **kw):
        call = Call(list(messages), tools)
        self.calls.append(call)
        assert self.script, "provider called more times than scripted"
        return self.script.pop(0)(call)

    async def stream(
        self, messages, tools=None, temperature=0.7, max_tokens=4096
    ) -> AsyncIterator[str]:
        raise NotImplementedError
        yield ""

    @property
    def name(self) -> str:
        return "scripted"

    @property
    def model(self) -> str:
        return "claude-haiku-5-5"

    @property
    def max_context_tokens(self) -> int:
        return 200_000


@pytest.fixture
def provider():
    p = ScriptedProvider()
    set_llm_factory(lambda model: p)
    return p


# ---------------------------------------------------------------------------
# Tool workflows and their stub actions
# ---------------------------------------------------------------------------

SEARCH_YAML = """
name: "Web Research"
description: "Search the web."
tags: ["web", "research"]
use_when: "You need facts from the internet."
first_task: search
result_key: summary
inputs:
  type: object
  required: [goal]
  properties:
    goal: {type: string, description: "The query"}
tasks:
  search:
    name: "Search"
    action: fake_search
"""

PLAIN_YAML = """
name: "Plain Helper"
description: "A workflow with no inputs block."
tags: ["misc"]
first_task: work
result_key: summary
tasks:
  work:
    name: "Work"
    action: fake_search
"""

FAILING_YAML = """
name: "Broken Tool"
description: "Always fails."
tags: ["misc"]
first_task: work
tasks:
  work:
    name: "Work"
    action: fake_fail
"""

HUMAN_YAML = """
name: "Ask Human"
description: "Asks a person."
tags: ["misc"]
first_task: ask
result_key: summary
tasks:
  ask:
    name: "Ask"
    auto: false
  answer:
    name: "Answer"
    action: fake_search
routings:
  - from: ask
    to: answer
"""

DEFINE_YAML = """
name: "Define Workflow"
description: "Stub of the system define workflow."
tags: ["system"]
first_task: create
result_key: created_workflow
tasks:
  create:
    name: "Create"
    action: fake_creator
"""

HAIKU_YAML = """name: "Haiku Writer"
description: "Writes haiku."
tags: ["creative"]
first_task: write
result_key: summary
tasks:
  write:
    name: "Write"
    action: fake_search
"""


class FakeSearchAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        goal = context.process.properties.get("goal")
        context.set_process_property("summary", f"results for {goal}")
        context.set_process_property("__total_cost__", 0.02)
        context.set_process_property("__total_tokens__", 300)
        context.set_process_property(
            "__token_history__", [{"input": 200, "output": 100, "total": 300, "cost": 0.02}]
        )
        return TaskResult.ok(output="searched")


class FakeFailAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.fail("tool exploded")


class FakeCreatorAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        library = context.extras["__workflow_library__"]
        name = library.add_workflow(HAIKU_YAML, llm_defined=True)
        created = {"name": name, "yaml": HAIKU_YAML}
        context.set_process_property("created_workflow", created)
        return TaskResult.ok(output=created)


@pytest.fixture
def library(tmp_path: Path) -> WorkflowLibrary:
    lib = WorkflowLibrary(tmp_path / "workflows")
    lib.ensure_initialized()
    for filename, text in {
        "web.yaml": SEARCH_YAML,
        "plain.yaml": PLAIN_YAML,
        "broken.yaml": FAILING_YAML,
        "human.yaml": HUMAN_YAML,
        "define.yaml": DEFINE_YAML,
    }.items():
        (lib.library_path / filename).write_text(text)
    return lib


@pytest.fixture
def metrics() -> InMemoryMetricsStore:
    return InMemoryMetricsStore()


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def registry() -> ActionRegistry:
    reg = ActionRegistry()
    reg.register_defaults()
    reg.register_action("llm_agent", LLMAgentAction)
    reg.register_action("fake_search", FakeSearchAction)
    reg.register_action("fake_fail", FakeFailAction)
    reg.register_action("fake_creator", FakeCreatorAction)
    return reg


@pytest.fixture
def engine(store, registry, library, metrics) -> WorkflowEngine:
    return WorkflowEngine(
        store,
        registry,
        extras={"__workflow_library__": library, "__metrics_store__": metrics},
    )


def agent_definition(**props) -> ProcessDefinition:
    properties = {"prompt": "{{goal}}", "output_key": "answer", "idempotent": True, **props}
    return ProcessDefinition(
        id=f"agent_{abs(hash(repr(sorted(props.items(), key=str))))}",
        name="Agent Under Test",
        first_task_id="research",
        properties={"result_key": "answer"},
        tasks={
            "research": TaskDefinition(
                id="research", name="Research", action="llm_agent", properties=properties
            )
        },
    )


async def run_agent(engine: WorkflowEngine, definition: ProcessDefinition, **process_props):
    props = {"goal": "What is new?", "__llm_model__": "low", **process_props}
    process = await engine.create_process(definition, properties=props)
    return await engine.start_process(process.id)


async def children_of(store: InMemoryStore, process_id: str):
    return [
        p
        for p in await store.list_processes(include_completed=True)
        if p.parent_process_id == process_id
    ]


def tool_messages(call: Call) -> list[Message]:
    return [m for m in call.messages if m.role == MessageRole.TOOL]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_tool_slug():
    assert tool_slug("Web Research") == "web_research"
    assert tool_slug("  Read: Web Page! ") == "read_web_page"
    assert len(tool_slug("x" * 100)) == 64


async def test_calls_a_workflow_tool_as_a_subflow(engine, store, provider, metrics):
    provider.script = [use(("web_research", {"goal": "zebra news"})), say("Answer [1](https://a)")]

    process = await run_agent(engine, agent_definition(tools=["Web Research"]))

    assert process.state == ProcessState.COMPLETE
    assert process.properties["answer"] == "Answer [1](https://a)"

    # Tool offered with the workflow's inputs schema
    (tool,) = provider.calls[0].tools
    assert tool.name == "web_research"
    assert tool.parameters["required"] == ["goal"]
    assert "Use when: You need facts from the internet." in tool.description

    # One child process, linked to the agent task, ran the workflow
    (child,) = await children_of(store, process.id)
    assert child.state == ProcessState.COMPLETE
    assert child.parent_task_id is not None
    assert child.properties["goal"] == "zebra news"
    assert child.properties[DEPTH_KEY] == 1
    assert child.properties["__llm_model__"] == "low"

    # The child's result went back to the model
    (result_msg,) = tool_messages(provider.calls[1])
    assert result_msg.content == "results for zebra news"
    assert result_msg.tool_call_id == "call_web_research_0"

    # Transcript in the task output
    output = process.properties["__task_output_research"]
    assert output["turns"] == 1
    (entry,) = output["transcript"]
    assert entry["tool"] == "web_research"
    assert entry["workflow"] == "Web Research"
    assert entry["process_id"] == child.id
    assert entry["success"] is True

    # Cost rolled up: child's $0.02 plus the agent's own two calls
    assert process.properties["__total_cost__"] > 0.02
    assert process.properties["__total_tokens__"] == 300 + 150 + 120
    assert len(process.properties["__token_history__"]) == 3

    # The tool run counts towards the workflow's stats, at zero cost
    stats = await metrics.get_stats("Web Research")
    assert stats.total_runs == 1
    assert stats.successful_runs == 1
    (run,) = await metrics.get_recent_runs(limit=5)
    assert run.cost == 0.0
    assert run.id == child.properties["run_id"]
    assert run.goal == "[tool] zebra news"


async def test_workflow_without_inputs_takes_a_goal(engine, provider):
    provider.script = [use(("plain_helper", {"goal": "do it"})), say("done")]

    process = await run_agent(engine, agent_definition(tools=["Plain Helper"]))

    assert process.state == ProcessState.COMPLETE
    assert provider.calls[0].tools[0].parameters == DEFAULT_INPUTS


async def test_unknown_tool_gets_an_error_and_no_child(engine, store, provider):
    provider.script = [use(("made_up", {"goal": "x"})), say("sorry")]

    process = await run_agent(engine, agent_definition(tools=["Web Research"]))

    assert process.state == ProcessState.COMPLETE
    assert await children_of(store, process.id) == []
    (error,) = tool_messages(provider.calls[1])
    assert error.content.startswith("Error: Unknown tool 'made_up'")
    assert "web_research" in error.content


async def test_failed_tool_is_reported_and_the_model_recovers(engine, provider):
    provider.script = [use(("broken_tool", {"goal": "x"})), say("worked around it")]

    process = await run_agent(engine, agent_definition(tools=["Broken Tool"]))

    assert process.state == ProcessState.COMPLETE
    (error,) = tool_messages(provider.calls[1])
    assert error.content == "Error: the workflow failed: tool exploded"
    assert process.properties["__task_output_research"]["transcript"][0]["success"] is False


async def test_parallel_tool_calls_resume_once(engine, store, provider):
    provider.script = [
        use(("web_research", {"goal": "a"}), ("web_research", {"goal": "b"})),
        say("both"),
    ]

    process = await run_agent(engine, agent_definition(tools=["Web Research"]))

    assert process.state == ProcessState.COMPLETE
    assert len(await children_of(store, process.id)) == 2
    assert len(provider.calls) == 2
    assert [m.content for m in tool_messages(provider.calls[1])] == [
        "results for a",
        "results for b",
    ]


async def test_parallel_tool_calls_are_capped(engine, store, provider):
    provider.script = [
        use(*[("web_research", {"goal": f"q{i}"}) for i in range(3)]),
        say("done"),
    ]

    process = await run_agent(
        engine, agent_definition(tools=["Web Research"], max_parallel_tools=2)
    )

    assert process.state == ProcessState.COMPLETE
    assert len(await children_of(store, process.id)) == 2
    results = [m.content for m in tool_messages(provider.calls[1])]
    assert len(results) == 3
    assert sum(r.startswith("Error: Too many tool calls") for r in results) == 1


async def test_turn_limit_fails_the_task(engine, provider):
    provider.script = [use(("web_research", {"goal": f"q{i}"})) for i in range(3)]

    process = await run_agent(engine, agent_definition(tools=["Web Research"], max_tool_turns=2))

    assert process.state == ProcessState.FAILED
    assert "Stopped after 2 tool turns" in process.properties["__error__"]


async def test_answer_on_budget_answers_without_tools_instead_of_failing(engine, store, provider):
    def final(call: Call) -> LLMResponse:
        assert call.tools is None
        assert "used your tool budget" in call.messages[-1].content
        return say("Best answer from q0 and q1")(call)

    provider.script = [use(("web_research", {"goal": f"q{i}"})) for i in range(3)] + [final]

    process = await run_agent(
        engine,
        agent_definition(tools=["Web Research"], max_tool_turns=2, answer_on_budget=True),
    )

    assert process.state == ProcessState.COMPLETE
    assert process.properties["answer"] == "Best answer from q0 and q1"
    # The over-budget turn's tool call was dropped, never run.
    assert len(await children_of(store, process.id)) == 2


async def test_define_workflow_then_call_it(engine, store, provider, library):
    def call_new_tool(call: Call) -> LLMResponse:
        assert "haiku_writer" in [t.name for t in call.tools]
        assert "Now available as the tool 'haiku_writer'".lower() in (
            tool_messages(call)[0].content.lower()
        )
        return use(("haiku_writer", {"goal": "autumn"}))(call)

    provider.script = [
        use((DEFINE_TOOL, {"goal": "write haiku", "suggested_name": "Haiku Writer"})),
        call_new_tool,
        say("An autumn haiku"),
    ]

    process = await run_agent(engine, agent_definition(allow_define_workflow=True))

    assert process.state == ProcessState.COMPLETE
    assert DEFINE_TOOL in [t.name for t in provider.calls[0].tools]
    info = next(w for w in await library.list_workflows() if w.name == "Haiku Writer")
    assert LLM_DEFINED_TAG in info.tags
    definitions = {c.definition_id for c in await children_of(store, process.id)}
    assert library.get_workflow("Haiku Writer").id in definitions
    assert library.get_workflow("Define Workflow").id in definitions


async def test_define_tool_is_opt_in(engine, provider):
    provider.script = [say("no tools needed")]

    await run_agent(engine, agent_definition(tools=["Web Research"]))

    assert [t.name for t in provider.calls[0].tools] == ["web_research"]


async def test_no_library_runs_without_tools(store, registry, provider):
    engine = WorkflowEngine(store, registry)
    provider.script = [say("plain answer")]

    process = await run_agent(engine, agent_definition(tools=["Web Research"]))

    assert process.state == ProcessState.COMPLETE
    assert provider.calls[0].tools is None
    assert process.properties["answer"] == "plain answer"


async def test_depth_limit_runs_without_tools(engine, provider):
    provider.script = [say("too deep for tools")]

    process = await run_agent(
        engine, agent_definition(tools=["Web Research"], max_depth=2), **{DEPTH_KEY: 2}
    )

    assert process.state == ProcessState.COMPLETE
    assert provider.calls[0].tools is None


async def test_model_cannot_set_internal_child_properties(engine, store, provider):
    provider.script = [use(("web_research", {"goal": "q", "__user_id__": 999})), say("ok")]

    process = await run_agent(engine, agent_definition(tools=["Web Research"]), __user_id__=1)

    (child,) = await children_of(store, process.id)
    assert child.properties["__user_id__"] == 1


async def test_survives_a_restart_mid_tool_call(store, registry, library, metrics, provider):
    extras = {"__workflow_library__": library, "__metrics_store__": metrics}
    first = WorkflowEngine(store, registry, extras=extras)
    provider.script = [use(("ask_human", {"goal": "favourite colour?"})), say("Blue, they said")]

    process = await run_agent(first, agent_definition(tools=["Ask Human"]))

    assert process.state == ProcessState.RUNNING
    (task,) = await store.load_tasks_for_process(process.id)
    assert task.state == TaskState.AWAITING_SUBFLOW
    assert task.properties[STATE_KEY]["pending"]

    # Restart: a new engine recovers, the task stays suspended, the human answers.
    second = WorkflowEngine(store, registry, extras=extras)
    await second.resume_all_processes()
    (child,) = await children_of(store, process.id)
    (human,) = await second.get_pending_tasks(child.id)
    await second.complete_task(human.id, TaskResult.ok())

    process = await store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    assert process.properties["answer"] == "Blue, they said"
    assert len(provider.calls) == 2


class _TagLibrary:
    def __init__(self, infos: list[WorkflowInfo]):
        self.infos = infos

    async def list_workflows(self):
        return self.infos

    def get_workflow(self, name):
        raise ValueError(name)


def _info(name: str, tags: list[str], rate: float) -> WorkflowInfo:
    return WorkflowInfo(
        name=name,
        description=name,
        tags=tags,
        version=1,
        definition_path=Path(f"{name}.yaml"),
        success_rate=rate,
    )


async def test_tool_tags_rank_by_success_rate_cap_and_skip_system():
    library = _TagLibrary(
        [
            _info("Low", ["web"], 0.2),
            _info("High", ["web"], 0.9),
            _info("Mid", ["web"], 0.5),
            _info("Internal", ["web", "system"], 1.0),
            _info("Agent Under Test", ["web"], 1.0),
            _info("Other", ["misc"], 1.0),
        ]
    )
    definition = agent_definition(tool_tags=["web"], max_tag_tools=2)
    task = TaskInstance(
        id="t",
        process_id="p",
        task_definition_id="research",
        foe_id="f",
        properties=dict(definition.tasks["research"].properties),
    )
    from zebra.core.models import ProcessInstance

    context = ExecutionContext(
        engine=None,
        store=None,
        process=ProcessInstance(id="p", definition_id=definition.id),
        process_definition=definition,
        task_definition=definition.tasks["research"],
        extras={"__workflow_library__": library},
    )

    tools = await LLMAgentAction()._select_tools(task, context)

    assert [t["workflow"] for t in tools.values()] == ["High", "Mid"]
