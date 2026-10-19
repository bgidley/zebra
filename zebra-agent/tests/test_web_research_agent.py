"""Web Research Agent: an llm_agent that calls the web workflows as tools (#146).

Runs the real built-in workflows (``web_research_agent``, ``web_search``,
``read_web_page``) with stubbed Kagi actions and a scripted model.
"""

from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskInstance, TaskResult
from zebra.definitions.loader import load_definition, validate_definition
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.llm.action import LLMCallAction
from zebra_tasks.llm.agent import LLMAgentAction
from zebra_tasks.llm.base import LLMProvider, LLMResponse, TokenUsage, ToolCall
from zebra_tasks.llm.client import set_llm_factory

from zebra_agent.library import WorkflowLibrary, list_goal_workflows

WORKFLOWS = Path(__file__).parent.parent / "workflows"
SOURCE = "https://example.org/zebra-stripes"


class StubKagiSearch(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        query = context.resolve_template(task.properties["query"])
        results = [{"title": "Why zebras have stripes", "url": SOURCE, "snippet": query}]
        context.set_process_property(task.properties["output_key"], results)
        return TaskResult.ok(output={"results": results})


class StubKagiExtract(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        url = context.resolve_template(task.properties["url"])
        markdown = f"# Page at {url}\nStripes confuse biting flies."
        context.set_process_property(task.properties["output_key"], markdown)
        return TaskResult.ok(output={"markdown": markdown})


def _response(content: str = "", tool_calls: list[ToolCall] | None = None) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason="tool_use" if tool_calls else "end_turn",
        usage=TokenUsage(200, 80),
        model="claude-haiku-5-5",
    )


class ResearchModel(LLMProvider):
    """Agent turns when tools are offered; the Web Research summariser otherwise."""

    def __init__(self):
        self.agent_turns = 0
        self.tool_results: list[str] = []

    async def complete(self, messages, tools=None, temperature=0.7, max_tokens=4096, **kw):
        if not tools:
            return _response(f"Stripes deter flies, see [study]({SOURCE}).")
        self.agent_turns += 1
        self.tool_results = [m.content for m in messages if m.role.value == "tool"]
        if self.agent_turns == 1:
            return _response(tool_calls=[ToolCall("s1", "web_research", {"goal": "zebra stripes"})])
        if self.agent_turns == 2:
            return _response(tool_calls=[ToolCall("r1", "read_web_page", {"url": SOURCE})])
        return _response(f"Stripes confuse biting flies.\n\nSources:\n- {SOURCE}")

    async def stream(self, *args, **kwargs):
        raise NotImplementedError
        yield ""

    @property
    def name(self) -> str:
        return "research-model"

    @property
    def model(self) -> str:
        return "claude-haiku-5-5"

    @property
    def max_context_tokens(self) -> int:
        return 200_000


@pytest.fixture
def library(tmp_path: Path) -> WorkflowLibrary:
    lib = WorkflowLibrary(tmp_path / "workflows")
    lib.copy_builtin_workflows(WORKFLOWS)
    return lib


@pytest.mark.parametrize(
    "filename",
    ["web_research_agent.yaml", "read_web_page.yaml", "define_workflow.yaml", "web_search.yaml"],
)
def test_workflow_is_valid(filename):
    assert validate_definition(load_definition(WORKFLOWS / filename)) == []


async def test_read_web_page_is_tool_only(library):
    names = {w["name"] for w in await list_goal_workflows(library)}

    assert "Read Web Page" not in names
    assert "Define Workflow" not in names
    assert {"Web Research", "Web Research Agent"} <= names


async def test_answers_with_cited_urls_via_tool_subflows(library):
    model = ResearchModel()
    set_llm_factory(lambda m: model)
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("llm_agent", LLMAgentAction)
    registry.register_action("llm_call", LLMCallAction)
    registry.register_action("kagi_search", StubKagiSearch)
    registry.register_action("kagi_extract", StubKagiExtract)
    store = InMemoryStore()
    engine = WorkflowEngine(store, registry, extras={"__workflow_library__": library})

    process = await engine.create_process(
        library.get_workflow("Web Research Agent"),
        properties={
            "goal": "Why do zebras have stripes?",
        },
    )
    process = await engine.start_process(process.id)

    assert process.state == ProcessState.COMPLETE
    assert SOURCE in process.properties["answer"]
    assert model.agent_turns == 3
    assert model.tool_results == [
        f"Stripes deter flies, see [study]({SOURCE}).",
        f"# Page at {SOURCE}\nStripes confuse biting flies.",
    ]

    children = {
        (await store.load_definition(p.definition_id)).name: p
        for p in await store.list_processes(include_completed=True)
        if p.parent_process_id == process.id
    }
    assert set(children) == {"Web Research", "Read Web Page"}
    assert children["Read Web Page"].properties["url"] == SOURCE
    assert all(c.state == ProcessState.COMPLETE for c in children.values())

    transcript = process.properties["__task_output_research"]["transcript"]
    assert [t["tool"] for t in transcript] == ["web_research", "read_web_page"]
    # The summariser's spend inside Web Research rolled up into the agent's process.
    assert process.properties["__total_tokens__"] == 280 * 4
