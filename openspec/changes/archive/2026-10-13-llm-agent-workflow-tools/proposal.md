## Why

LLM tasks cannot use tools. The provider layer supports tool calling, but `llm_call` never passes tools and has no tool loop. Zebra's tools should be its own workflows, so every tool call is a tracked, costed process that feeds the learning loop. Today a task that runs a sub-workflow has to hold a coroutine and poll (`subworkflow`, `wait_subworkflow`), so a long tool call would pin the caller and could not survive a restart (#146).

## What Changes

- **Engine: suspend on subflow.** New task state `AWAITING_SUBFLOW` and `TaskResult.suspend(children=[...])`. The engine persists the pending child ids, starts the children, and when every child is terminal re-runs the task's action with the child results in `context.subflow_results`. Survives restarts: recovery starts never-started children and resumes tasks whose children finished while the engine was down.
- **Workflow input contract.** Optional top-level `inputs:` (JSON Schema) on workflow YAML, kept in `ProcessDefinition.properties["inputs"]` and exposed as `WorkflowInfo.inputs`. Without it a workflow takes `{goal: string}`. The output is the existing `result_key`.
- **`llm_agent` action.** An LLM task whose tools are workflows (`tools` names and/or `tool_tags`). Each tool call spawns a child process and the task suspends until it returns. Transcript kept in task properties between turns; tool cost rolled up into the calling process; bounded by `max_tool_turns` and a recursion depth limit.
- **`define_workflow` tool** (opt-in, `allow_define_workflow`). Runs the new system workflow *Define Workflow* as a subflow: ethics gate, then `workflow_creator`, which validates and saves the workflow (tagged `llm-defined`). The new workflow is callable on the next turn.
- **Workflows.** `web_search.yaml` gains `inputs:`; new `read_web_page.yaml` (Kagi extract), `define_workflow.yaml` (system) and `web_research_agent.yaml` (answers a question with cited URLs).

## Capabilities

### New Capabilities
- `subflow-suspension`: engine-level suspend/resume of a task on child processes.
- `llm-agent-tools`: workflows as LLM tools, the `llm_agent` action, workflow input schemas and LLM-defined tools.

### Modified Capabilities
None.

## Impact

- `zebra-py`: `core/models.py`, `core/engine.py`, `tasks/base.py`, `definitions/loader.py`.
- `zebra-tasks`: new `llm/agent.py`, entry point `llm_agent`.
- `zebra-agent`: `library.py` (`WorkflowInfo.inputs`), new workflows.
- No DB migration: task state is a free-form string column.
