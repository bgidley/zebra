## 1. Engine: suspend on subflow

- [x] 1.1 `TaskState.AWAITING_SUBFLOW`, `TaskResult.suspend()`, `ExecutionContext.subflow_results`
- [x] 1.2 `_run_task`: persist suspension; build subflow results on resume; keep pending ids until the run ends
- [x] 1.3 Start pending children after the parent lock is released; child-terminal hook resumes the parent
- [x] 1.4 Recovery: start never-started children; resume tasks whose children finished
- [x] 1.5 Engine tests: suspend → complete → resume, failed child, parallel children, human-task child, restart recovery

## 2. Workflow input contract

- [x] 2.1 Loader keeps top-level `inputs:` in properties; `WorkflowInfo.inputs`
- [x] 2.2 Tests

## 3. llm_agent action

- [x] 3.1 `zebra_tasks/llm/agent.py`: tool selection, transcript, spawn + suspend, resume, cost roll-up, limits, depth
- [x] 3.2 `define_workflow` tool via *Define Workflow* subflow; new workflow offered next turn
- [x] 3.3 Entry point `llm_agent`
- [x] 3.4 Unit tests with a fake provider, in-memory store and small library

## 4. Workflows

- [x] 4.1 `web_search.yaml` `inputs:`; `read_web_page.yaml`; `define_workflow.yaml` (system); `web_research_agent.yaml`
- [x] 4.2 Integration test of the web research agent with stubbed Kagi actions and a scripted provider

## 5. Docs

- [x] 5.1 `specs/llm-agent-tools-design.md`, `specs/AGENTS.md`, `specs/zebra-as-is.md`, package AGENTS.md files
