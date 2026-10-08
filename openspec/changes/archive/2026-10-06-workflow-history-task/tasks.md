# Tasks

Branch: `f138/workflow-history-task` (convention `fN/short-description`). Commits reference #138.

## 1. Store query

- [x] 1.1 Add abstract `search_runs(since, until, text, workflow_name, success, limit)` to `MetricsStore` in `zebra-agent/zebra_agent/storage/interfaces.py`, with default limit 20 and cap 200; verify by importing it (`uv run python -c "from zebra_agent.storage.interfaces import MetricsStore"`)
- [x] 1.2 Implement `search_runs` in `InMemoryMetricsStore` and write tests in `zebra-agent/tests/test_metrics.py` for the date window (start inclusive / end exclusive), case-insensitive text, combined filters, newest-first ordering and the limit cap; verify `uv run pytest zebra-agent/tests/test_metrics.py -k search_runs` passes
- [x] 1.3 Implement `search_runs` in `DjangoMetricsStore` (`goal__icontains`, `started_at` range, user scoping) and write tests in `zebra-agent-web/tests/unit/test_metrics_search_runs.py`, covering user A not seeing user B's runs; verify `uv run pytest zebra-agent-web/tests/unit/test_metrics_search_runs.py` passes

## 2. `get_workflow_history` action

- [x] 2.1 Add a relative/ISO time parser (`-7d`, `24h`, `30m`, `2w`, ISO-8601 → UTC datetime; an unsigned offset means the past; invalid input raises) in `zebra-tasks/zebra_tasks/agent/history.py`, with unit tests in `zebra-tasks/tests/test_workflow_history.py`; verify the parser tests pass
- [x] 2.2 Implement `GetWorkflowHistoryAction` (templatable filter inputs, `output_key` default `workflow_history`, compact runs with output/error truncated to ~300 characters, `history_context` capped at ~4,000 characters, resolved `filters`, current `run_id` excluded, empty result when the store is missing, failure on an invalid time, `reversibility_hint = always_reversible`); verify the tests in `test_workflow_history.py` for relative window, no matches, store unavailable, invalid time and bounded output pass
- [x] 2.3 Register the `get_workflow_history` entry point in `zebra-tasks/pyproject.toml`, run `uv sync --all-packages`, and verify the IoC registry resolves it (test: registry lookup)

## 3. `assess_history_need` action

- [x] 3.1 Implement `AssessHistoryNeedAction` in `zebra-tasks/zebra_tasks/agent/history.py`: a keyword cue pre-check, then a Haiku JSON call returning `{needs_history, since, until, text, reasoning}`, routing `needs_history` or `no_history`, and degrading to `no_history` on an LLM error or bad JSON; verify the tests (using the `_testing` mock provider) for the past-work goal, the ordinary goal making no LLM call, and LLM failure pass
- [x] 3.2 Register the `assess_history_need` entry point, run `uv sync --all-packages`, and verify the registry resolves it

## 4. Wiring into the agent main loop

- [x] 4.1 Add an optional `history_context` input to `workflow_selector` that renders a `## Workflow History` prompt section when non-empty; verify by extending `zebra-tasks/tests/test_selector_knowledge.py` (or a sibling test) to assert the section appears only when the input is provided
- [x] 4.2 Append a delimited `## Workflow history` section to the child goal in `execute_goal_workflow._spawn_child` when `workflow_history.history_context` is set; verify with tests that the goal is unchanged when it is absent and augmented when it is present
- [x] 4.3 Update `zebra-agent/workflows/agent_main_loop.yaml` to v9: add the `assess_history_need` and `get_workflow_history` tasks and their routings (`consult_knowledge → assess_history_need`, `needs_history → get_workflow_history → ethics_input_gate`, `no_history → ethics_input_gate`) and pass `history_context` to `select_workflow`; verify with an engine-level test in `zebra-agent/tests/` that runs both routes with mocked LLM and in-memory stores and checks the child goal
- [x] 4.4 Verify the existing main-loop and loop tests still pass (`uv run pytest zebra-agent/tests/test_loop.py zebra-tasks/tests -q`)

## 5. Docs

- [x] 5.1 Document both actions in `zebra-tasks/README.md`, and update `specs/zebra-as-is.md` §4 Catalogue, §5 Agent main loop (v9 flow) and §5 Metrics (`search_runs`); verify the docs mention both action names and the v9 loop
- [x] 5.2 Verify `openspec validate workflow-history-task --strict` passes

## 6. Integration & delivery

- [x] 6.1 Run lint and format (`uv run ruff check --fix . && uv run ruff format .`) and verify `uv run ruff check .` is clean
- [x] 6.2 Run the full suite (`uv run pytest`) and verify it is green
- [x] 6.3 Submit to Zebra feedback (prod `run_goal`, sonnet) and apply any genuine gaps; verify the feedback is addressed or rebutted in the commit message
- [x] 6.4 Hand the branch to `cicd-manager` for CI, archive and merge (`Closes #138`); verify the master pipeline is green
