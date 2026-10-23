# LLM tool use via workflows (#146)

Specs: [subflow-suspension](../openspec/specs/subflow-suspension/spec.md), [llm-agent-tools](../openspec/specs/llm-agent-tools/spec.md) (change archived as `2026-10-13-llm-agent-workflow-tools`).

## 1. Goal & scope

An LLM task can call tools, and **every tool is a Zebra workflow**. A tool call runs the workflow as a child process. It therefore gets the same tracking, cost roll-up, metrics and dream-cycle learning as any other run. The LLM never calls an external API or MCP server directly; that only happens inside a workflow's task actions. If no workflow fits, the model can define one (`define_workflow`), and it is saved and callable on the next turn.

Not in scope: per-tool-call timeouts (the goal's `GOAL_TIMEOUT_SECONDS` bounds the whole run), MCP tools (they belong below the workflow layer, as task actions), streaming.

## 2. Data model changes

| Where | Change |
|---|---|
| `TaskState` | New `AWAITING_SUBFLOW` (`"awaiting_subflow"`). The DB column is a free-form string, so no migration is needed. |
| `TaskResult` | `suspend_children: list[str] \| None`; `TaskResult.suspend(children)`. |
| `ExecutionContext` | `subflow_results: list[dict] \| None`, one per child, in order: `process_id`, `workflow`, `success`, `output` (child's `result_key` value, else `__output__`), `error`, `properties`. |
| Task property `__pending_subflows__` | The child ids a suspended task waits for. Kept until the resumed run ends. |
| Task property `__agent_state__` | `llm_agent` conversation: `messages`, `tools` (`{slug: {workflow, description, parameters}}`), `turns`, `pending`, `transcript`. |
| Process property `__agent_depth__` | Tool-call nesting depth (children get parent + 1). |
| Workflow YAML `inputs:` | JSON Schema of the workflow's arguments. The loader copies it to `ProcessDefinition.properties["inputs"]`, like `result_key`. `WorkflowInfo.inputs`. No `inputs` means `{goal: string}`. |

## 3. API / interface changes

- **Engine:** an action returns `TaskResult.suspend([...child ids])`. The children are processes it created with `parent_process_id` / `parent_task_id` set (left `CREATED`, so the engine starts them after persisting the suspension).
- **`llm_agent` action** (`zebra_tasks/llm/agent.py`, entry point `llm_agent`). Properties: `prompt` / `system_prompt` / `messages`, `tools` (workflow names), `tool_tags` + `max_tag_tools` (default 8, ranked by `success_rate`, system workflows excluded), `allow_define_workflow`, `max_tool_turns` (8), `max_parallel_tools` (4; extra calls in a turn get an error result), `max_depth` (3), `output_key` (`agent_response`), plus `llm_call`'s `model` / `provider` / `temperature` / `max_tokens` / `response_format`. Output: `{response, transcript, turns, tools}`. Declare `idempotent: true` so recovery re-runs an interrupted turn. With `response_format: json` the final answer must parse (via `parse_llm_json`) to an object or array; otherwise it is asked for once more with no tools (`complete_json`'s notes; 2× `max_tokens` when truncated) and, if still unusable, the task fails with the cause and the start of the reply, leaving `output_key` unset (#216).
- **Tool names** are slugs of workflow names (`Web Research` → `web_research`). The definition is the workflow's `description` + `use_when` and its `inputs` schema.
- **`list_goal_workflows`** excludes *tool-only* workflows (`inputs.required` names anything other than `goal`).
- **Workflows:** `web_search.yaml` v2 gains `inputs`. New: `read_web_page.yaml` (tool-only, `kagi_extract`), `define_workflow.yaml` (system: `ethics_gate` → `workflow_creator`; reject/escalate → `propagate_failure`), `web_research_agent.yaml`.

## 4. Control flow

```
llm_agent run ── model asks for tools ──► create child processes (CREATED)
                                          return TaskResult.suspend(ids)
engine: task → AWAITING_SUBFLOW (+ __pending_subflows__), save process
        release the parent lock, then start each CREATED child
child COMPLETE/FAILED ──► _on_process_terminal ──► all children terminal?
        └─ yes: task → READY; if this engine is driving the parent process,
                the driver runs it after unlocking (_run_resumed_tasks);
                otherwise transition_task(task) now
resumed run: context.subflow_results ─► tool_result messages, cost roll-up,
             tool run recorded in metrics ─► next model turn (repeat or finish)
```

- **No nesting inside the parent's lock.** Locks are re-entrant per engine and an inner release would drop the outer lock. So children start, and resumed tasks run, only after `transition_task` releases its lock. `WorkflowEngine._driving` counts the processes this engine is driving, and `_deferred` holds the resumed tasks a driver runs once it unlocks.
- **Resumed once.** Only the caller that moves the task `AWAITING_SUBFLOW → READY` runs it. Within an engine, one check per task runs at a time and a completion arriving mid-check forces a recheck. Across engines the move happens under the parent process's lock.
- **Cancellation.** `fail_process` on a parent also fails the non-terminal children its suspended tasks were waiting on (`Parent process … failed: …`), so a cancelled or timed-out goal leaves no orphan tool runs or human tasks.
- **A failed child is a result.** The model sees `Error: the workflow failed: …` and decides what to do. Unknown tools get an error tool result and no child.
- **Recovery:** `resume_all_processes` leaves `AWAITING_SUBFLOW` tasks alone (they are not `RUNNING`). `_reconcile_subflow_waits` starts children that never left `CREATED` and resumes waits whose children finished while the engine was down. Children are recovered first (children-first order), so their completion resumes the parent.
- **Cost:** each child's `__total_cost__` / `__total_tokens__` / `__token_history__` is added to the calling process, so `execute_goal_workflow` reports the full goal cost.
- **Metrics:** every tool child gets its own `run_id` and is recorded as a `WorkflowRun` (`goal: "[tool] …"`, **cost 0**, since the cost is already in the calling goal and counting it twice would distort the daily budget). The workflow's `success_rate` and `use_count` therefore count its use as a tool.
- **LLM-defined workflows** are kept: `workflow_creator` saves them tagged `llm-defined`. The dream-cycle curator (#148) tidies them up.
- **Safety:** tool workflows run their own trust gates. `define_workflow` is opt-in and passes the ethics gate (a dilemma counts as a refusal; a tool call can't wait for a human). The model can't set `__` properties on children; user identity and LLM provider/model are copied from the caller. Depth is limited, and the running workflow is never offered as a tool to itself.

## 5. Configuration

No new settings. Limits are task properties (`max_tool_turns`, `max_depth`, `max_tag_tools`).

## 6. Open questions / risks

- Tool children run inline in the same call stack, as `subworkflow` does, so the goal timeout bounds them. The task holds no coroutine, which is what lets human-in-the-loop tools and restarts work.
- Tool runs appear in the runs list (marked `[tool]`). If that gets noisy, filter them in the web views.
- A tool child parked on a human task is treated like any human task: the goal timeout covers only the inline auto-task chain, and the daemon hands the goal off as awaiting a human (the process-tree search finds the child's task).
- LLM-defined workflows can be picked up by `tool_tags`. That is the same exposure as goal selection today; `workflow_creator`'s prompt keeps side-effecting actions out unless asked and puts a human task in front of them.
- The issue asks for LLM-defined workflows to carry the id of the run that created them; only the `llm-defined` tag is stored today.
- `subworkflow` / `wait_subworkflow` still poll; moving them to `TaskResult.suspend` is tracked in #181.
