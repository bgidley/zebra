# Zebra — As-Is Design

**Date**: 2026-06-04
**Status**: Snapshot of current implementation
**Companion**: [../docs/requirements.md](../docs/requirements.md) describes the target vision; this document describes what exists today.

---

## 1. Overview

Zebra is a declarative, workflow-driven AI agent platform. Every agent behaviour — from answering a question to rewriting its own workflows — executes as a YAML-defined process through a common workflow engine. It is delivered as a UV monorepo of four Python packages:

| Package | Role | LOC (approx) |
|---|---|---|
| `zebra-py` | Core workflow engine, state model, loaders, forms | ~1,200 in engine alone |
| `zebra-tasks` | Pluggable task actions (LLM, filesystem, agent, ethics) | ~40 modules |
| `zebra-agent` | Agent loop, memory, metrics, workflow library, budget, CLI | ~3,700 |
| `zebra-agent-web` | Django web UI, daemon host, storage backends, diagram viewer | ~4,000 |

A legacy Java implementation sits in `legacy/` and is archived.

---

## 2. Architectural Layers

```
┌─────────────────────────────────────────────────────────────┐
│ zebra-agent-web (Django + Daphne ASGI + Channels)           │
│   - Views, templates, WebSocket consumers                   │
│   - DjangoStore / DjangoMemoryStore / DjangoMetricsStore    │
│   - DaemonStarterMiddleware → budget daemon                 │
└─────────────────────────────────────────────────────────────┘
                        ▲
┌─────────────────────────────────────────────────────────────┐
│ zebra-agent (Agent library)                                 │
│   - AgentLoop (thin wrapper over agent_main_loop.yaml)      │
│   - WorkflowLibrary, BudgetManager, Scheduler               │
│   - IoCActionRegistry (dependency-injector)                 │
│   - CLI (list/stats/help/quit)                              │
│   - In-memory Memory/Metrics stores for standalone use      │
└─────────────────────────────────────────────────────────────┘
                        ▲
┌─────────────────────────────────────────────────────────────┐
│ zebra-tasks (Plug-in task actions via entry points)         │
│   - llm_call, subworkflow, parallel_subworkflows, …         │
│   - filesystem (read/write/copy/move/delete/search)         │
│   - python_exec                                             │
│   - agent (consult_memory, workflow_selector, dream cycle,  │
│            ethics_gate, queue_goal, assess_and_record, …)   │
└─────────────────────────────────────────────────────────────┘
                        ▲
┌─────────────────────────────────────────────────────────────┐
│ zebra-py (Core engine)                                      │
│   - WorkflowEngine, Process/Task state machines, FOE        │
│   - StateStore (InMemory, SQLite, Postgres)                 │
│   - Pydantic definition/instance models                     │
│   - Definition loader (YAML/JSON)                           │
│   - JSON Schema → form conversion                           │
│   - Template resolution ({{var}}, {{task.output.key}})      │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Core Engine (`zebra-py`)

### State machines

- **Process lifecycle**: `CREATED → RUNNING → COMPLETE` (with `PAUSED`, `FAILED`). When no active tasks remain and any task is `FAILED` (returned `TaskResult.fail` / raised, so never routed), the process ends `FAILED` with `__error__` = the task's error and `__failed_task__` = its definition id (#131); only an all-`COMPLETE` drain ends `COMPLETE`. Handled failures (success + `next_route`) route and complete normally.
- **Task lifecycle**: `PENDING → AWAITING_SYNC → READY → RUNNING → COMPLETE` / `FAILED`.
- **Suspend on subflow (#146)**: an action returns `TaskResult.suspend([child ids])`; the task waits in `AWAITING_SUBFLOW` (pending ids in `__pending_subflows__`), the engine starts the children after releasing the parent's lock, and when all are terminal re-runs the action with `context.subflow_results`. A failed child is a result, not a task failure; failing the parent fails every live child linked by `parent_process_id`, waited on or not (`StateStore.list_child_processes()`, #185); a task is resumed once even when children finish together. A finished child resumes its `parent_task_id` and any other suspended task of its parent process listing it, e.g. `wait_subworkflow` on a child another task started (#181). Recovery starts never-started children and resumes waits that finished while down. See [llm-agent-tools-design.md](llm-agent-tools-design.md).
- **Flow of Execution (FOE)**: tracks parallel branches. Serial routings inherit the parent FOE; parallel routings fork new FOEs. Synchronised (`synchronized: true`) tasks wait for all incoming FOEs via backward-reachability.

### Routing

- Implicit serial/parallel edges declared in YAML.
- Conditional routing via `TaskResult.ok(output=..., next_route="name")` matching a `routings[].name` entry. Used by ethics gates, workflow selection, memory checks.
- Built-in conditions: `AlwaysTrueCondition`, `RouteNameCondition` — anything else requires a registered custom condition.

### Storage

- `StateStore` abstract interface covers definitions, instances, FOEs, locking, the step journal and `list_child_processes`.
- **Step journal (#184)**: the engine appends a `ProcessEvent` at process start/end and task waiting/start/suspend/complete/fail, each with the process-property diff since the previous event (`zebra/core/journal.py`; values over 16k chars stored as a preview). Replaying a process's events rebuilds its properties after any step. Best effort: a write failure only logs. Stores without a journal (the base-class default) keep working with no history. See [run-trace-design.md](run-trace-design.md).
- Implementations: `InMemoryStore` (tests), `SQLiteStore`, `PostgresStore`.
- **JSON-serialisation is enforced at the Pydantic layer** — non-serialisable objects cannot be placed in process properties. Services pass through `engine.extras` instead (the IoC escape hatch).

### Definition model

- `ProcessDefinition` / `TaskDefinition` are **frozen** Pydantic models. YAML or JSON loaders produce them.
- Top-level `result_key` and `inputs` (JSON Schema of the workflow's arguments when called as a tool, #146) are copied into `ProcessDefinition.properties`.
- Template resolution is regex-based: `{{var}}` and `{{task_id.output.key}}`. No arithmetic, no conditionals, no loops inside templates.

### Human tasks & forms

- Convention-based: `auto: false` + a JSON Schema under `properties.schema`. No action runs; the task sits `READY` until externally completed.
- `zebra.forms` converts JSON Schema to a `FormSchema` (list of `FormField`), with `coerce_form_data` and `validate_form_data` helpers. Enum fields can drive named routes (e.g., approve / reject).
- **Generated forms (#179):** `schema` may instead be a single `{{reference}}` (`{{key}}`, `{{key.field}}`, `{{task_id.output}}`) to a JSON Schema an earlier task wrote, typically an `llm_call` with `response_format: json`, so follow-up questions become one field each. `zebra.forms.resolve_task_schema()` resolves it; every schema reader (web form/submit/task lists, complete-task and pending-tasks APIs, `execute_goal_workflow` `user_inputs`) uses it. An unresolvable reference falls back to the single `response` field. The workflow creator prompt teaches the pattern and `check_generated_workflow` rejects non-reference schema strings. See `openspec/specs/dynamic-human-forms/spec.md`.

### Strengths

- Clean separation of definition (immutable) vs. instance (mutable).
- Fully async; storage and actions are pluggable.
- Serialisation contract catches bad property writes early.
- FOE model handles arbitrary fork/join topologies.

### Weaknesses / gaps

- **MCP server advertised in the README but not present** in `zebra-py/zebra/mcp/` — the requirements spec (Appendix B) references this path, but no code lives there today.
- **Template language is weak** — no expressions beyond dotted key lookup.
- **No retry / backoff** in the engine. `execution_attempt` counts recovery interruptions: interrupted non-idempotent tasks are flagged `__requires_manual_review__` and can be retried (`WorkflowEngine.retry_task`) or failed from the activity / run detail pages and REST API; recovery fails a process once a task hits `RECOVERY_MAX_INTERRUPTED_ATTEMPTS` (default 3). See [f8-crash-recovery.md](f8-crash-recovery.md) (#130).
- **Postgres backend is thinner than SQLite** — less test coverage, feature-completeness unclear.

---

## 4. Task Actions (`zebra-tasks`)

### Catalogue

| Category | Actions |
|---|---|
| LLM | `llm_call`, `llm_agent` (#146: workflows as tools; each tool call is a child process the task suspends on; `define_workflow` runs the *Define Workflow* system workflow; transcript in the output; child cost rolled up; tool runs recorded as zero-cost `WorkflowRun`s — see [llm-agent-tools-design.md](llm-agent-tools-design.md)) |
| Subtasks | `subworkflow`, `wait_subworkflow`, `parallel_subworkflows` — start their children (inline run bounded by `timeout`) and suspend on them (`TaskResult.suspend`), building `{success, process_id, properties, output}` / `{success: false, process_id, error}` from `subflow_results` on resume; `wait_subworkflow` only waits on children of its own process and ignores `timeout`; `parallel_subworkflows` keeps child keys in `__subflow_keys__` and with `fail_fast` starts no more children once one fails (#181) |
| Filesystem | `file_read`, `file_write`, `file_copy`, `file_move`, `file_delete`, `file_search`, `file_exists`, `file_info` (9 actions) |
| Compute | `python_exec` (sandboxed) |
| Agent loop | `consult_memory`, `consult_knowledge`, `assess_history_need`, `get_workflow_history` (F138 — see [workflow-history spec](../openspec/specs/workflow-history/spec.md)), `workflow_selector`, `workflow_creator`, `workflow_variant_creator`, `execute_goal_workflow`, `assess_and_record`, `update_conceptual_memory`, `propagate_failure`, `record_metrics`, `load_workflow_definitions`, `queue_goal` — `workflow_creator`/`workflow_variant_creator` cap output at `GENERATED_WORKFLOW_MAX_TOKENS` (12000 — sized to finish inside the 180s LLM timeout) and reject truncated or `validate_definition`-invalid (orphaned tasks) YAML, or `route_name` routings from `llm_call` tasks, before saving (#122, #139); both share `generate_workflow()`, which makes one follow-up call: a truncated reply is re-requested (without the cut-off YAML) asking for a more compact workflow, any other problem is fed back for repair (#188); the variant prompt forbids copying previous-run content into the YAML; `workflow_creator` runs at temperature 0.3, and its prompt documents data flow, serial/parallel/`synchronized` routing and that `route_name` routes are human-task buttons (#139) |
| Outcome review (#190) | `zebra_source` (read-only read/search of Zebra's own source, sandboxed to the checkout; tools *Read Zebra Source* / *Search Zebra Source*), `compare_outcome_reviews` (per-outcome Zebra vs Claude verdicts → `agreed` / `disputed` / `ruled`). See [outcome-review-design.md](outcome-review-design.md) |
| Dream cycle | `metrics_analyzer`, `workflow_curator`, `workflow_evaluator`, `workflow_optimizer`, `review_knowledge` (#153), `propose_zebra_improvements` (#189) |
| Ethics | `ethics_gate` |
| Knowledge (F32, F152, F153) | `review_knowledge` (dream-cycle review, see Dream cycle), `add_knowledge`, `decay_confidence`, `pick_entries_for_verification`, `apply_verification_result`, `apply_resolution`, `extract_knowledge` (haiku extraction of personal-fact candidates; no writes; reusable), `store_learned_knowledge` (stores candidates as `source=agent`, conflicts → *Resolve Knowledge Contradiction* process; `update_agent_entries` updates a conflicting agent entry in place instead — F155) — see [knowledge-learning spec](../openspec/specs/knowledge-learning/spec.md) |
| Web (F115, #145, F155) | `kagi_search`, `kagi_extract` — Kagi v1 API (`POST /api/v1/search`, `/extract`, Bearer `KAGI_API_KEY`); `kagi_summarize` removed (v1 has no summarizer). `kagi_news_fetch` (public news.kagi.com `kite.json` feed, no key) and `kagi_news_read` (one batch Kagi Extract call, falls back to Kagi News summaries) |
| Notifications (F65) | `notify_email` (SMTP, `ZEBRA_SMTP_*` env), `notify_webhook` (HTTP POST/PUT, `ZEBRA_NOTIFY_WEBHOOK_URL`) — both `always_irreversible` |

### LLM integration

- Provider abstraction supports **Anthropic Claude** (primary), **OpenAI**, **Kimi** and **OpenRouter** (#182), registered lazily via a factory registry.
- Pricing table hardcoded in `pricing.py` (per-1M-token Anthropic/Kimi rates); Sonnet defaults for unknowns. Providers that report a call's cost (OpenRouter's `usage.cost` → `TokenUsage.cost_usd`) bypass the table via `usage_cost()`.
- Every call updates process properties: `__total_cost__`, `__total_tokens__`, `__token_history__`.
- Soft budget warnings via an injected `__budget_manager__` (non-blocking).

### Registration

- Entry points in `pyproject.toml` under `[project.entry-points."zebra.tasks"]` — loaded by `importlib.metadata` at startup. No imperative registration required.

### Weaknesses

- **Agent actions are coupled to `zebra-agent`** (import its memory / library / metrics types). Soft-decoupled via `context.extras`, but still a layering leak.
- **Subtasks don't roll up cost** — child `__total_cost__` isn't propagated into the parent automatically for all paths. (The web daemon does its own propagation in `assess_and_record`; `llm_agent` rolls up its tool children.)
- **Ethics gate is advisory** — it only evaluates; workflows must explicitly route on its output to block.
- **No structured-output guarantees** on LLM calls — JSON is extracted post-hoc by regex.
- **Filesystem actions have minimal sandboxing** — path sanitisation only; no whitelist.

---

## 5. Agent Library (`zebra-agent`)

### Agent main loop (declarative)

The loop lives in `workflows/agent_main_loop.yaml`, not Python. `AgentLoop` is a ~200-line wrapper that starts the workflow and awaits it. The loop:

```
consult_memory
  → consult_knowledge
  → assess_history_need      (needs_history → get_workflow_history — F138; continuations always ask the LLM — #150)
  → ethics_input_gate
  → assess_continuation      (F135)
  → workflow_selector
  → [create_new | create_variant | use_existing]
  → flag_concerns            (advisory, non-blocking — F21)
  → ethics_plan_review       (escalate → resolve dilemma → record — F22)
  → execute_goal_workflow    (continue_on_failure — #140)
  → assess_stuck             (failed + help budget left → stuck_help_request → apply_help_response — #176)
  → assess_and_record
  → write_postmortem         (failed runs only: lesson into memory — #175)
  → update_conceptual_memory
  → ethics_post_review       (llm_call)
  → record_ethics_review     (audit check_type=post_review — #143)
  → extract_knowledge        (F152 — skips with no __user_id__; no_candidates → report_outcome)
  → store_learned_knowledge  (source=agent, confidence ≤ 0.5; conflicts → resolve-contradiction process)
  → report_outcome           (propagate_failure — #140)

any gate "reject" → ethics_rejection (record_ethics_rejection — #143)
```

**Failed goal runs are learned from (#140)**: `execute_workflow` sets `continue_on_failure: true`, so a failed/timed-out child completes the task with `execution_result.success = false` and `error` instead of failing it. `assess_and_record` (given `error`), `update_conceptual_memory`, `ethics_post_review` and `record_ethics_review` therefore run for failures too, recording a `WorkflowRun` with `success=false` and a workflow-memory entry. The terminal `report_outcome` task (`propagate_failure`) then fails with the child's error, so the main-loop process still ends `FAILED` with `__error__` = child error (`__failed_task__` = `report_outcome`). Failures before execution (selection, creation, gate errors) are still not recorded.

**"I'm stuck" handoff (#176)**: before that recording, `assess_stuck` (`zebra_tasks/agent/stuck.py`) parks a failed run on the `stuck_help_request` human task while fewer than `max_help_requests` (2) requests have been made (`__help_requests__`). Haiku writes the request (what I tried / where I'm stuck / what I need, from the error and `__task_executions__`) into `help_request` and `help_request_display`; without an LLM a plain request is built from the error. `apply_help_response` routes on the answer: `retry` loops back to `execute_workflow` (a fresh task, so a new child), with `__help_history__` appended to the child goal by `with_help_guidance`; `redirect` sets `goal` to the user's text (`original_goal` keeps the first) and returns to `ethics_input_gate`; `abandon` suffixes the error "(abandoned after asking for help)" and continues to the #140 record-then-fail path. With the budget spent a failure behaves as before. Only goal-workflow failure is detected; low-confidence and no-progress detection are not built. See `openspec/changes/archive/2026-10-15-stuck-handoff/`.

**Postmortem journal (#175)**: after `assess_and_record`, `write_postmortem` (`zebra_tasks/agent/postmortem.py`) has haiku write what happened, the root cause and an actionable lesson for a failed run and stores it as a `PostmortemEntry` (`MemoryStore.add_postmortem`, table `zebra_postmortems`, one per run). Goals that end FAILED without reaching that step (goal timeout, crash, gate error; not the kill switch) get one from the *Postmortem* system workflow, started by the daemon's reconcile and by `AgentLoop`; rating a run 1 or 2 starts it in the background with the user's feedback (`trigger` = `failure` / `timeout` / `low_rating`). `consult_memory` recalls up to 3 lessons relevant to the goal (`search_postmortems`: Oracle embeddings, else keyword overlap) into `memory_context` and `lessons_context`; `execute_goal_workflow` appends them to the child goal as `<lessons>` (`with_lessons`). `/journal/` lists them newest first in Zebra's voice. No LLM → no lesson. Lessons cannot yet be edited or pruned. Design: [postmortem-journal-design.md](postmortem-journal-design.md).

**Personal knowledge is learned from goal runs (F152)**: after the post-execution review, `extract_knowledge` asks haiku for durable facts the user stated about themselves. Its inputs are the goal, `execution_result.user_inputs` (the child's human-task answers without read-only fields), `continuation_comment` and the result. It returns up to 5 `{category, key, value, time_sensitive, confidence}` candidates. Keys are normalised to snake_case and existing keys are offered for reuse. Credential- or card-like values are always dropped, and LLM-flagged special-category data is dropped unless `ZEBRA_KNOWLEDGE_ALLOW_SENSITIVE` / `allow_sensitive` is set. `store_learned_knowledge` writes each candidate through `store_knowledge_entry()` (the shared core of `add_knowledge`) as `source="agent"` with confidence capped at 0.5, below the 0.6 weekly-verification threshold. A re-observed value keeps `max(old, new)` confidence. A conflicting value (human or agent) is never written: it starts a top-level *Resolve Knowledge Contradiction* process, deduplicated by a `__knowledge_contradiction__` marker. `/knowledge/` shows source and confidence, hides soft-deleted entries, and has **Confirm** (`POST /knowledge/<id>/confirm/` → confidence 1.0, source human). Learning runs for failed goals too; goals without `__user_id__` make no LLM call.

### Dream cycle (`dream_cycle.yaml`)

Self-improvement loop: `metrics_analyzer` → `workflow_curator` → `load_workflow_definitions` → `workflow_evaluator` → `workflow_optimizer` → `review_knowledge` → `propose_zebra_improvements` → summary. Runs over the last N days of metrics; can propose edits to stored workflows. `workflow_optimizer` parses and validates every created/modified workflow before saving it (library loader, `check_generated_workflow`, registered actions). It caps output at `GENERATED_WORKFLOW_MAX_TOKENS` and retries a truncated response once at `TRUNCATION_RETRY_MAX_TOKENS` (14000, inside the 180s LLM timeout; #188). Rejected changes are not saved and go to `failed_changes` instead of `changes_made`; the v3 summary prompt reports them as not applied (#128).

- **F136 continuation analysis**: `metrics_analyzer` walks continuation chains in the window (`get_continuations_since` → `get_run_chain` → `get_task_executions`, logic in `zebra_tasks/agent/continuation_analysis.py`) and emits `continuation_analysis` (chains, frequently continued workflows, `new_workflow` capability gaps, added steps, `source: continuation` proposals) plus per-workflow `continuation_rate`. The evaluator merges those proposals into `improvement_priorities`; the optimizer applies them first, through the #128 validation, and reports `continuation_changes`. The v4 summary has a "Continuations" section. Lineage fields may be `None`; store errors degrade to an empty block. The same rate is also kept for all time in `WorkflowStats.continued_runs` / `continuation_rate` (both stores), shown as a "Continued" card on the workflow page, as "N% continued" in the dashboard and library lists, and in API workflow stats (#137).
- **F153 knowledge review**: `review_knowledge` (`zebra_tasks/knowledge/review.py`) runs after the optimizer. The window starts at the previous completed Dream Cycle process (same definition id), else `lookback_days` (7). Runs are grouped by the new `WorkflowRun.user_id` (set by `assess_and_record` from `__user_id__`; the Django store reads/writes the `user_id` column), so users with no runs, and unowned runs, cost no LLM call. Per user (max 20, most active first), one LLM call sees the active entries and up to 20 runs (goal, outcome, rating, continuation comment, answers to the workflow's `auto: false` tasks from task executions) and proposes `new` / `update` / `stale` / `merge` / `reinforce`. Rules: agent entries change directly (update → confidence 0.7; stale → confidence ×0.5 capped at 0.5, so weekly verification picks it up; reinforce → `last_verified` now, +0.1 up to 0.9; merge → soft-delete the duplicate); new facts follow `add_knowledge` semantics (`source="agent"`, confidence ≤0.9, normalised snake_case key; a key clash becomes an update). `source="human"` entries are never written: a conflicting value starts *Resolve Knowledge Contradiction*, stale or duplicate human entries start *Knowledge Verification* with `review_entry_ids` (which `pick_entries_for_verification` now honours); pending proposals are not duplicated (contradictions carry F152's `__knowledge_contradiction__` marker, so per-run learning and the review never double-prompt). Max 10 changes per user. The `knowledge_review` output (counts, examples, `changes` audit trail with before/after, errors) stays on the dream-cycle process; `revert_knowledge_changes()` undoes the direct changes. The v6 summary has a "Knowledge" section. The step never fails the cycle. Spec: [dream-knowledge-review](../openspec/specs/dream-knowledge-review/spec.md).
- **#189 Zebra improvement requests**: `propose_zebra_improvements` (`zebra_tasks/agent/improvements.py`, haiku) runs after the knowledge review. It sends the cycle's findings (evaluator key issues and priorities, continuation capability gaps, the optimizer's `failed_changes`; each clipped, max 10 per kind) and the titles of every earlier request to one LLM call, which returns only problems needing a change to Zebra's code (area `engine` / `task_action` / `web_ui` / `storage` / `llm` / `other`), not a workflow edit. No findings → no LLM call. Each valid proposal, up to `max_requests` (2), whose normalised title (lower case, punctuation collapsed) matches no earlier request in any state, starts a *Zebra Improvement Request* process (`workflows/zebra_improvement_request.yaml`, system): properties `improvement`, `improvement_title`, `improvement_markdown`, `source_process_id`, `__improvement_request__`, `__user_id__` when the cycle has one; one human task `review` with verdict `accepted` / `rejected` / `duplicate` / `later`, optional `issue_url` and `notes`. Output `improvement_requests = {requests, skipped, errors}`; the v7 summary has an "Improvements requested" section. Never fails the cycle. Earlier requests are found across every stored version of the request workflow (`store.list_definitions()` by name; #194), but `DjangoStore.list_processes` still scopes them to the current user for user-started cycles (#193). **Filing (#194)**: request workflow v2 routes `review → file_issue` (`file_improvement_issue`): verdict `accepted` with no reviewer link → `POST {ZEBRA_GITLAB_URL}/api/v4/projects/{ZEBRA_GITLAB_PROJECT}/issues` (default `https://gitlab.com`, `gidley/zebra`; `PRIVATE-TOKEN: ZEBRA_GITLAB_TOKEN`; 15s) with the request markdown, reviewer notes, the dream-cycle process id and a `zebra-request:<process id>` marker, label `dream-request`. A search for that marker (`state=all`, exact backtick-wrapped match) first adopts an existing issue, so a recovery re-run never files twice; a failed search records an error and files nothing; `filed_issue.url` already set skips. Lines starting with `/` are backslash-escaped (no quick actions) and `@` gets a zero-width space (no mentions). Result `filed_issue = {url, iid} | {skipped} | {error}`; never fails the request, the token is never stored or logged. v1 requests in flight finish without filing. Spec: `openspec/specs/dream-improvement-requests/spec.md`.
- **History page**: `/dreams/` (`api/dream_history.py`) reads Dream Cycle process instances straight from the ORM (not user-scoped; scheduled cycles have no user) and flattens their step reports (`metrics_analysis`, `curation`, `evaluation`, `optimization_results`, `improvement_requests`, `dream_summary`) for display, with the `dream_cycle` routine's next run, and lists recent *Zebra Improvement Request* processes (status, verdict, issue link — the reviewer's, else the one Zebra filed, "Issue I filed" — or the filing error, Review link to the human task). Spec: [dream-cycle-history-page](../openspec/specs/dream-cycle-history-page/spec.md).

### Daily news reading (F155)

The `daily_news_reading` routine (`zebra-agent-web/fixtures/routines/daily_news_reading.yaml`, 07:00 UTC) queues a goal that requests the **Daily News Reading** workflow (`workflows/daily_news_reading.yaml`): `consult_knowledge` → `kagi_news_fetch` (World, Business, Technology, Science; ≤10 stories each) → `llm_call` (haiku picks exactly 5 `{id, reason}`) → `kagi_news_read` → `llm_call` writes the digest (`result_key: digest`) → `llm_call` (haiku) extracts ≤8 `world` knowledge candidates with story-topic keys → `store_learned_knowledge` (`max_confidence: 0.7`, `update_agent_entries: true`). The knowledge store holds **world knowledge** as well as personal facts: the `world` category (90-day decay half-life, migration `0025`) is user-scoped like the rest. A developing story updates its agent entry in place; a conflict with a human entry still goes to *Resolve Knowledge Contradiction*. Spec: [daily-news-reading](../openspec/specs/daily-news-reading/spec.md).

### Memory

Three-tier model (matches the design in REQ-DATA-004):

| Tier | Interface | Implementations | Typical size |
|---|---|---|---|
| Working (process properties) | `ExecutionContext` | in-engine | unbounded per run |
| Episodic (`WorkflowMemoryEntry`) | `MemoryStore` | `InMemoryMemoryStore`, `DjangoMemoryStore` | last 5 / workflow; 5 most similar goals at selection |
| Conceptual (`ConceptualMemoryEntry`) | `MemoryStore` | same | 10 most goal-relevant entries into LLM |

**Goal-relevant retrieval (#169)**: `consult_memory` asks `MemoryStore.search_conceptual_memories(goal)` and `search_workflow_memories(goal)` (adding a "Similar Past Goals" section and the workflows of similar successful runs to the shortlist); `consult_knowledge` asks `PersonalKnowledgeStore.search_entries(user_id, goal)`. On Oracle these rank by **in-database embeddings**: an ONNX model (Oracle's prebuilt all-MiniLM-L12-v2, 384 dims, loaded from the `zebra-models` OCI bucket via the database resource principal by `manage.py load_embedding_model`) and per-table triggers keep an `embedding VECTOR` column filled; search orders by `VECTOR_DISTANCE` (cosine, cut-off `MEMORY_VECTOR_MAX_DISTANCE`). Elsewhere, and whenever the model isn't loaded, the interface defaults rank recent entries by keyword overlap. Design: [memory-vector-embeddings-design.md](memory-vector-embeddings-design.md).

### Metrics

`MetricsStore` records workflow runs, task executions, tokens, USD cost, and user ratings. Two implementations (in-memory, Django). `get_total_cost_since()` feeds the budget manager. `search_runs()` (F138) filters runs by `since`/`until`/goal text (any keyword from `search_keywords()`, #150)/workflow/success, newest first, limit ≤200; the Django store scopes to an explicit `user_id` or the request user.

### Workflow library

`WorkflowLibrary` loads YAMLs from `~/.zebra-agent/workflows/`, caches them, tracks success rate and use count. Workflows tagged `system` are internal and never offered for goals.

**Curation (#148).** Workflows written by the LLM (`workflow_creator`, `workflow_variant_creator`, and the optimizer's creates) are tagged `llm-defined` (`add_workflow(llm_defined=True)` / `tag_llm_defined`). A workflow the optimizer modifies keeps the provenance of the original.

`retire(name, reason, superseded_by)` moves a YAML to `retired/` and appends the metadata after a marker comment. It's soft and reversible with `restore(name)`.

**Unparseable files (#158).** Before every scan of the active library (`list_workflows`, `_files_named`, `list_workflow_files`), `quarantine_unparseable()` moves any `*.yaml` that does not parse, or is not a mapping, to `retired/<stem>.unparseable.yaml`. The file becomes a parseable stub: `name: "<name> [unparseable]"`, tag `unparseable`, the raw text in `unparseable_content`, and retirement reason `unparseable: <error>`. It is logged once and never re-parsed. It shows in the retired list but is never selected, and `restore()` refuses it (409 in the UI). Built-in workflow directories are not scanned. `add_workflow` rejects unparseable or non-mapping YAML (`parse_workflow_yaml`). The prod case, `fire_retirement_calculator_1.yaml`, was written by the optimizer on 2026-10-02 before its YAML validation (`744453e`). Retired workflows are not in `list_workflows`, so the selector, the LLM context and the dream cycle never see them. `get_workflow` / `get_workflow_yaml` still resolve them, so history and continuations keep working, and `copy_builtin_workflows` never brings back a retired built-in. When several active files share a name (the optimizer saves modified workflows as `foo_1.yaml`), the newest file wins.

The dream cycle's `workflow_curator` runs before `load_workflows`. Rules, in priority order:
- **broken:** the definition fails to load or validate.
- **superseded_copy:** an older same-name file.
- **failing:** `runs >= min_runs` and success below `min_success_rate`.
- **unused:** `llm-defined` only; no run, or if never run no file change, within `unused_days`.
- **duplicate:** an LLM finds the pair; the weaker one (lower success rate, then fewer runs) is retired if it is `llm-defined`.

Workflows tagged `system`, and the core system names, are never touched. A per-cycle cap defers the rest, and dry run changes nothing. Settings come from task properties, then `ZEBRA_CURATOR_*` env vars (`MIN_RUNS` 5, `MIN_SUCCESS_RATE` 0.3, `UNUSED_DAYS` 30, `MAX_RETIRE_PER_CYCLE` 5, `DRY_RUN` false, `DETECT_DUPLICATES` true). The `curation` report feeds the v5 summary.

The web library page lists retired workflows with a Restore button. The detail page has Retire / Restore buttons and a retired banner (`/workflows/<name>/retire/`, `/restore/`). Spec: [workflow-curation](../openspec/specs/workflow-curation/spec.md).

`list_goal_workflows(library)` (`zebra_agent/library.py`) is the single builder of the selector's candidates: one dict per non-`system`, non-tool-only workflow (tool-only = `inputs.required` names anything but `goal`, e.g. *Read Web Page*; #146) (`name`, `description`, `tags`, `success_rate` float, `use_count`, `use_when`). `AgentLoop.process_goal`, the web/daemon `api/goals.queue_goal` helper and the `queue_goal` action all use it for `available_workflows`. At selection time `workflow_selector` rebuilds the list from the live `__workflow_library__` (falling back to the queued property), so queued goals see workflows added since; the prompt shows "N/A" success for never-run workflows (#144).

### Budget

`BudgetManager` enforces daily USD limits with linear time-of-day pacing (`allowed = daily * hours_elapsed / 24`). Soft warnings only; no hard block mid-run. Stateless — it reads live from `MetricsStore`.

### IoC

`ZebraContainer` (dependency-injector) plus `IoCActionRegistry` inspect action `__init__` signatures and inject services automatically. Entry-point discovery makes adding a new action zero-config.

### CLI

Minimal: `/list`, `/stats`, `/help`, `/quit`. Launch with `zebra-agent` / `python -m zebra_agent.cli`. No trust, values, knowledge, or budget commands yet.

### Ethics gates

Three checkpoints wired into `agent_main_loop.yaml`: input gate, plan review, post-execution review. Implementation is LLM-prompt-based Kantian reasoning (universalizability, rational beings as ends, autonomy). The post-execution review is advisory and automated (no human confirmation since F111).

**Ethics outcome recording (#143, loop v10).** Every ethics verdict is now durable and visible:
- `record_ethics_review` normalises `ethics_post_assessment` to `{ethical, overall_reasoning, concerns, recommendations}` and appends an `EthicsAuditEntry` with `check_type="post_review"`. An unparseable review fails closed (`ethical=false`).
- The review runs *after* `update_conceptual_memory`, so a failed review no longer skips the memory update.
- The terminal `ethics_rejection` task runs `record_ethics_rejection`. It stores `ethics_rejection = {gate, reasoning, concerns}`, where `gate` is `input_gate`, `plan_review` or `dilemma_resolution`. It writes no audit entry, because the gate already did.
- `AgentResult.ethics_rejection` carries the record, and `error` reads `Rejected by ethics <gate>: <reasoning>`.
- The run pages (`partials/ethics_outcome.html`) show the rejection or the post-review.
- Rejected goals still write no metrics `WorkflowRun`, so per-workflow success rates are unaffected. See `openspec/specs/ethics-outcome-recording/spec.md`.

`EthicsGateAction` accepts an optional `user_id` input. When provided and `__profile_store__` is available in `context.extras`, the gate loads the user's current `ValuesProfile` and incorporates it into a combined evaluation prompt. Kantian rejection always takes precedence (values can only restrict further). The stored assessment includes a `values_assessment` key (`null` for Kantian-only runs). Verdict log lines show both Kantian and values flags when a profile was consulted.

**Proactive concern flagging (F21 / REQ-ETH-004).** Between workflow selection and the plan-review gate, `flag_concerns` (`FlagConcernsAction`) runs an advisory, non-blocking LLM scan of the planned approach and records any concerns (`{description, severity, step}` + summary) on the root process as `planning_concerns`. It never routes to a rejection branch; the web run-detail view surfaces the concerns in an advisory panel. See [f21-concern-flagging.md](f21-concern-flagging.md).

**Dilemma escalation (F22 / REQ-ETH-005).** The plan-review gate now receives `user_id` (activating values-informed evaluation in the loop). When an action is Kantian-permissible but a genuine values conflict exists, `EthicsGateAction` emits a third verdict — `escalate` — instead of silently proceeding or rejecting. The loop pauses on the `ethics_dilemma_resolution` human task (both sides shown via `{{dilemma_display}}` + a proceed/decline decision); `record_dilemma_resolution` then records the choice to the ethics audit trail and routes accordingly. Deal-breaker and Kantian failures still reject decisively; with no profile loaded `escalate` is never emitted. See [f22-dilemma-escalation.md](f22-dilemma-escalation.md).

### Values profile (F18 / REQ-ETH-002)

Per-user profile of `core_values`, `ethical_positions`, `priorities`, and `deal_breakers` — free-form text plus structured tags. The data lives behind a new `ProfileStore` interface (`zebra_agent/storage/interfaces.py`) with `InMemoryProfileStore` and `DjangoProfileStore` backends.

- **Versioning.** Every save creates an immutable `ValuesProfileVersion` with a monotonic `version_number`; `ValuesProfileModel.current_version` points to the latest. Old versions are retained for audit.
- **Hybrid taxonomy.** Tags are field-scoped with `status ∈ {seeded, promoted, candidate, rejected, merged}`. The wizard's extract step asks an LLM to pick from the approved set (`seeded + promoted`) and to propose new candidates from the free-form text. When the user confirms a candidate, it is stored as a `candidate` row and its `usage_count` is incremented.
- **Taxonomy curation (#106).** `zebra_agent_web/values_taxonomy.py` is the curation module, used by both `manage.py values_taxonomy {list,promote,reject,demote,merge,prune}` and the `/profile/taxonomy/` page ("Values Tags" in the nav).
  - **Transitions:** promote (`candidate|rejected → promoted`), reject/archive (`candidate|promoted → rejected`), demote (`promoted → candidate`). Seeded tags are never curated.
  - **Merge:** folds a tag into another in the same field. Usage moves to the target, the source becomes `merged` with a `merged_into` pointer, and `record_confirmed_tags` counts later confirmations of the merged slug toward the target.
  - **Suggestions:** candidates with `usage_count ≥ VALUES_TAG_PROMOTION_THRESHOLD` (default 3) are flagged as suggested. They are never promoted automatically.
  - **Prune:** `prune` deletes stale single-use candidates (older than 90 days by default).
- **Wizard.** `zebra-agent/workflows/values_profile_wizard.yaml` is a system workflow with eight steps: load existing profile (auto), four free-form text forms (human tasks), extract tags via LLM (auto), review (human task), save (auto). Used for both first-time capture and edit mode (signalled by `existing_profile_version_id` in the initial process properties; load step pre-populates form defaults).
- **Bootstrap.** `manage.py bootstrap_values_taxonomy` calls an LLM to draft a starter taxonomy and writes a reviewable YAML fixture; the maintainer reviews and commits it, and a data migration loads it as `status="seeded"` on first `migrate`.
- **Web entry-point.** `/profile/values/` (`web_views.values_profile_wizard`) creates a wizard process for the authenticated user and redirects to the first pending task.
- **Wired into the ethics gate (F19).** `EthicsGateAction` reads the profile via `ProfileStore.get_current()` when `user_id` is supplied. Kantian precedence rule applied in Python.

### Strengths

- Declarative agent behaviour — YAML is editable, inspectable, version-controllable.
- Pluggable storage cleanly decouples task actions from database choice.
- Memory consolidation keeps LLM context bounded; goal-relevant retrieval uses Oracle's in-database embeddings, with no separate vector DB or embedding service (#169).
- Cost tracking is fine-grained and surfaced.

### Weaknesses

- **Standalone CLI loses all state on exit** — no SQLite default; only in-memory stores.
- **Dream cycle is experimentally powerful but only structurally validated**: LLM-driven mutations must parse and pass `validate_definition` and the action registry check (#128), but they are not gated by behavioural tests.
- **No trust model exists.** Requirements describe SUPERVISED / SEMI-AUTONOMOUS / AUTONOMOUS; implementation has none of this.
- ~~**No values profile** — ethics is generic Kantian, not personalised.~~ Resolved by F18 (data + UI) and F19 (ethics-gate consumption, REQ-ETH-003).
- ~~**No personal knowledge store** — only the three workflow-focused tiers.~~ Resolved by F31 (store, CRUD UI, agent loop integration) and F32 (lifecycle: decay, verification, contradiction detection, soft-delete).
- ~~**Only a goal scheduler, not a time/event scheduler**~~ — `GoalScheduler` (`zebra-agent/zebra_agent/scheduler/goal_queue.py`) picks the next CREATED process for the budget daemon. A cron/interval `SchedulerLoop` now fires built-in and user-defined routines (F27 / REQ-PRIN-008). There is **no event-driven trigger bus** (REQ-PRIN-009).
- ~~**Single-user implicit** — no `user_id` namespacing anywhere in stores or schemas.~~ Resolved by F6 (REQ-USR-002).
- **Agent main loop YAML is 258 lines** — hard to unit-test sub-branches.
- **Memory vector search is an exact scan** — no vector index (#169); fine for thousands of rows. Non-Oracle backends rank by keyword overlap over the 50 most recent entries.

---

## 6. Web UI (`zebra-agent-web`)

### Stack

- **Django 5 + Daphne + Channels**
- **HTMX 2.0.4 + Alpine.js 3.17.4**, vendored in `static/vendor/` (no CDN scripts)
- **Tailwind v4, compiled** by `scripts/build_css.py` (pinned standalone binary, sha256-checked, no Node) from `static/css/src/app.css` to `static/css/app.css` (generated, not committed). Built in the Dockerfile before `collectstatic` and by the `css` CI job (#159)
- **Design tokens** in `app.css` `@theme`: frame neutrals (`ground`, `surface`, `surface-2`, `line`, `ink`, `muted`, `faint`), states (`ok`, `fail`, `needs`) and `voice`, reserved for Zebra's own words (#161). Tailwind's `gray` scale is remapped to the same neutrals (#160). **Light mode** (#163): dark by default, light via `prefers-color-scheme`, which redefines every token and mirrors the gray scale; every text token meets WCAG AA in both themes (`tests/unit/test_theme.py`). No hard-coded hue classes remain; the workflow diagram uses the tokens too. Rules: [web-ui-design.md](web-ui-design.md)
- **Shell** (#160): sidebar with stripe mark, nav grouped core / Agent / Governance, a **Tasks** item whose needs-you badge (running goals waiting on a human task, via `_running_activities`) loads over HTMX from `/nav/needs-you/`, and the user + version info in its footer. Mobile top bar: menu, title, one Run goal action. Below `lg` the sidebar is hidden by `.app-sidebar` in CSS and Alpine only toggles `data-open`, so it is correct before deferred Alpine runs; the open menu locks page scroll and closes on Escape, backdrop tap or growing to `lg` (#166). `layouts/bare.html` (no nav) serves sign-in, passkey setup and first-run setup. `user` reaches templates through the `auth` context processor; `CurrentUserMiddleware` stores the resolved user on `request.user` in async requests
- **Shared components**: `.btn` / `.btn-primary` / `.btn-quiet` / `.btn-danger` / `.btn-sm`, `.panel`, `.zebra-mark` (CSS, `app.css`); `components/state_dot.html`, `components/certainty.html` (confidence to stripe density); `{{ value|usd }}` (`format_tags`: 2 dp, `<$0.01` below a cent)
- **Voice layer** (#161): the ethics gates, workflow selector, flag concerns, continuation assessor and post-run ethics review also ask for `voice` (first-person line) and `confidence` (0 to 1) in the same call (`zebra_tasks/agent/voice.py`; stored only when supplied; Agent Main Loop v15). `api/thoughts.py` derives ordered thoughts from a run's process properties (voice line, else the recorded reasoning, marked as such; confidence only when recorded) and a per-user recent feed. Shown as the run page **Thought trail**, the dashboard **On my mind** panel, and certainty stripes on Knowledge. No extra LLM calls; dream cycles don't record a voice yet
- **Fonts**: Geist + Geist Mono, self-hosted in `static/fonts/`
- **Icons**: `{% icon "name" %}` (`api/templatetags/icon_tags.py`) inlines vendored Phosphor regular SVGs from `zebra_agent_web/icons/phosphor/`; an unknown name renders nothing and logs an error. Nav, stat cards and shell use it; other pages still have inline SVGs
- **Django REST Framework** for JSON endpoints

### Routes

| Path | Purpose |
|---|---|
| `/` | Dashboard (#162): **Needs you** strip (goals waiting on a human task), vitals panel (spend vs paced budget via `_budget_bars()`, success rate, queue), Running Activities (#126) and Recent Runs; On my mind (#161), Trust by Domain and Top Workflows alongside |
| `/run/` | Goal submission: large goal field, compact model / priority / deadline row, Run now or Queue (#162) |
| `/activity/` | Recent runs (handles orphaned processes) |
| `/runs/<id>/` | Run detail with SVG workflow diagram; Final Output markdown rendered server-side (`markdown` template filter, markdown-it-py, raw HTML escaped — #149) |
| `/workflows/` | Library browser; `/workflows/<name>/` shows stats, ordered steps and a natural-width structure diagram (`_workflow_structure()`), with the YAML in a collapsed Definition disclosure (#162) |
| `/processes/<id>/trace/`, `/runs/<id>/trace/` | Step trace (#184): the whole run from its root down, subflows nested under the step that spawned them, per-step state/timing/changed properties, lazy "properties after this step" snapshots, "where it is now", live refresh (`api/run_trace.py`) |
| `/dreams/` | Dream Cycle history: last 20 cycles with health score, changes applied/rejected, retirements, continuations, improvements requested and the LLM summary; health trend; next scheduled run; recent Zebra improvement requests with Review links (#189) |
| `/bugs/` & `/bugs/report/` | Bug reports (#186): the sidebar **Report a bug** dialog posts the user's view plus browser context; the server adds build, user, route and linked process/run state and starts a system *Bug Report* process whose human review task records verdict, priority, issue link and notes. `/bugs/` lists reports. See [bug-report-design.md](bug-report-design.md) |
| `/tasks/` & `/tasks/<id>/` | Pending human tasks + JSON-Schema form |
| `/api/runs/<id>/diagram/` | SVG |
| `/api/tasks/<id>/complete/` | Submit human task |
| `/api/budget/` | Budget status |
| `/ws/goal/<run_id>/` | Live progress WebSocket |

### Daemon

In production, the budget daemon runs as a **separate `zebra-daemon` Quadlet unit** (`deploy/podman/quadlet/zebra-daemon.container`) to guarantee exactly one daemon instance. It starts via `python manage.py run_daemon` (no middleware needed).

In development/testing, `DaemonStarterMiddleware` spawns `run_daemon_loop()` via `asyncio.create_task()` on the first request (Daphne doesn't run ASGI lifespan events). Loop (each tick): `reconcile tracked goals → skip if one is still executing → pick_next → budget_check → start_process in a background task → wait until finished or parked on a human task → record metrics`.

**Human-task hand-off (#141)**: `start_process` runs auto tasks inline, so `_tick` runs it as a background task via `GoalTracker` (`zebra-agent/zebra_agent/scheduler/goal_tracker.py`) and stops waiting as soon as `find_pending_human_task` (`zebra_agent/human_tasks.py`) sees a READY `auto: false` task in the goal or any RUNNING descendant (e.g. the ethics dilemma form, or a human task in the executed child workflow). The goal stays tracked; later ticks log its `[daemon:done]`/`[daemon:fail]` outcome and `goals_completed` metric exactly once when it terminates. Pickup stays serial: a tracked goal still executing and not waiting on a human blocks the next pickup. Daemon-started goals carry `__daemon_started__`, and a restarted daemon re-tracks RUNNING ones. `AgentLoop.process_goal()` likewise returns `AgentResult(awaiting_input=True, error="Awaiting human input: <task>")` and emits `human_task_pending` instead of timing out. A human task in the executed child workflow ends the goal's background run too, since `execute_goal_workflow` suspends on the child (#185); before that the run kept polling and the goal timeout (#142) failed it.

**Goal timeouts (#142)**: `start_process` runs auto tasks inline, so every goal-path start goes through `WorkflowEngine.start_process_with_timeout`, which cancels the inline chain and `fail_process`es it on timeout, on a `cancel_check` reason, or when the caller is cancelled. Bounds: daemon (`GoalTracker(goal_timeout=…)`) and web `AgentLoop` per goal = `GOAL_TIMEOUT_SECONDS` (default 900s; `AgentLoop(goal_timeout=…)`, `DEFAULT_GOAL_TIMEOUT`); child goal workflow = `execute_goal_workflow` `timeout` (600s in the Agent Main Loop YAML); Dream Cycle = 600s. Time parked on a human task is not counted: `execute_goal_workflow` starts its child (bounded by `timeout`) and then suspends on it (`TaskResult.suspend`), so a goal whose child waits on a human returns from its bounded run, and the goal resumes and collects the child's output, cost/tokens, `user_inputs` and task executions when the child ends (#185). Before #185 it polled the child inline, so the goal timeout failed goals waiting on a human and left the child orphaned with live human tasks. The chain resumed by a human-task submit (`complete_task`) is not bounded by any start timeout; the engine discards the result of an action whose process was failed while it ran (`_run_task`), so a late return cannot route or revert the process to RUNNING (#183). Each LLM API attempt is bounded by `ZEBRA_LLM_TIMEOUT_SECONDS` (default 180s, 2 retries; `llm_request_timeout()` in `zebra_tasks/llm/base.py`) in every provider, so a stalled request fails inside a 600s goal instead of the SDKs' 600s default. See `openspec/specs/goal-execution-timeouts/spec.md`.

**Routine goals (F155)**: a `Routine` with `goal` (YAML `goal`, `goal_priority`, `run_as`) is dispatched by `queue_routine_goal` in `api/daemon.py`: `queue_goal()` with `extra_properties={"__routine__": name, "requested_workflow": workflow}`, running as `run_as` or the owner — the first active superuser, else the earliest-created active user (no user → user-scoped steps skip). `SchedulerLoop` skips (status `already_queued`) while a goal with the same `__routine__`, created in the last 20 hours (`PENDING_GOAL_MAX_AGE`), is `CREATED` or `RUNNING`. `workflow_selector` uses `requested_workflow` without an LLM call when it is in the library.

**Startup recovery (F8, #129)**: on start the daemon runs `engine.resume_all_processes()` as a *background* asyncio task (`recover_interrupted`) so re-driving recovered goals never delays the scheduler loop. Recovery goes children-first. The Agent Main Loop's `execute_workflow` task is `idempotent: true` and `execute_goal_workflow` records `__child_process_id__` on its task, so a goal whose driver died (e.g. an `/api/goals/` web thread killed by a redeploy) is reset to READY and re-attaches to its existing child workflow (suspending on it) instead of being flagged for manual review or spawning a duplicate. Each such interruption still counts toward `RECOVERY_MAX_INTERRUPTED_ATTEMPTS` (#130, passed to `recover_interrupted`), so a goal interrupted 3 times auto-fails. A goal suspended on its child (e.g. waiting on a human) is not RUNNING, so restarts do not count against it (#185). See [f8-crash-recovery.md](f8-crash-recovery.md).

### Storage backends (Django ORM)

- `DjangoStore` (workflow state — `ProcessInstanceModel`, `TaskInstanceModel`, `FlowOfExecutionModel`, `ProcessEventModel` step journal in `zebra_process_events`, #184)
- `DjangoMemoryStore`, `DjangoMetricsStore`
- Works against SQLite, PostgreSQL, Oracle (Oracle is the integration-test target).
- Oracle uses `zebra_agent_web.db_backends.oracle`, a thin subclass of Django's backend whose `ensure_connection()` pings a connection that has seen an error and reconnects if Oracle closed it. Needed because ORM calls run in `sync_to_async(thread_sensitive=False)` workers and the daemon, where Django's request-signal `close_old_connections()` never fires — without it a dropped session wedged prod until restart (#133).

### Forms

Server-side: reuses `zebra.forms` (`schema_to_form` + coerce/validate).
Template tag `{% render_schema_form %}` renders Tailwind-styled fields with per-field errors, required markers, route buttons.

### Kill switch (F2)

`POST /api/kill-switch/` sets a persisted `halted` flag in `SystemStateModel`. The daemon checks this flag before each goal pickup and while waiting on a goal — `GoalTracker.cancel_active` sets the executing goal's cancel reason, which `start_process_with_timeout` picks up as its `cancel_check` (#142), and its process is failed ("Kill switch activated") within a couple of seconds; goals parked on a human task are left alone. `python manage.py kill_switch --halt|--resume|--status` is the CLI equivalent. See [f2-kill-switch.md](f2-kill-switch.md).

### Observability (F3)

`structlog` JSON logging in production, `ConsoleRenderer` in development. Prometheus metrics at `/api/metrics/` (goals submitted/completed, budget gauges, queue depth). Health check at `/api/health/` (200 healthy / 503 unhealthy). `run_id` is logged inline by the daemon; per-request HTTP correlation IDs are not yet propagated. See [f3-observability.md](f3-observability.md).

### User identity & namespacing (F6)

`user_id = IntegerField` added to six ORM models (processes, tasks, runs, task executions, episodic/conceptual memory) via migration `0011_user_id_columns`. `CurrentUserMiddleware` propagates the authenticated user's PK via a `ContextVar` for the duration of each HTTP request. Django store implementations filter reads by `user_id` when one is in context. Abstract store interfaces (`MemoryStore`, `MetricsStore`) remain unchanged. See [f6-user-id-namespacing.md](f6-user-id-namespacing.md).

### Strengths

- Unified ORM for memory, metrics, state, and Django models across three DB engines.
- Live execution feedback over WebSockets.
- Zero-template-code human tasks via JSON Schema.
- Activity view falls back gracefully to process properties when a metrics record is missing.

### Authentication & Identity (F4 + F5)

- **Passkey (WebAuthn) authentication** on all web endpoints via `py_webauthn` and Django sessions.
- **First-run setup flow** (`SetupRedirectMiddleware`) captures display name and generates a stable local identity UUID, stored in `SystemStateModel`.
- Every process is stamped with `__user_display_name__` and `__user_identity_id__` at creation.
- **Goal submitter (#151).** Every goal entry point stamps `__user_id__` plus the identity keys on the Agent Main Loop process: `POST /api/goals/` (`execute_goal` → `_run_goal_in_background` → `AgentLoop.process_goal(user_id=, identity=)`), API/web continue, `/run/execute/`, `/run/queue/`, the `queue_goal` action (copied from the queuing process; `execute_goal_workflow` likewise copies them onto the child goal workflow via `zebra_tasks/agent/user_context.py`) and `zebra goal --user NAME` / `manage.py run_goal --user NAME`. Identity is read with `goal_identity_sync()` in sync views and `await goal_identity()` in async views (`api/identity.py`); the sync ORM call fails inside the event loop.
- See [f4-f5-identity-auth.md](f4-f5-identity-auth.md) for full detail.

### Weaknesses

- **No passkey management UI** — users cannot delete or rename registered passkeys.
- **No per-user isolation in all paths** — `clear_conceptual_memories` wipes all users (latent bug). See [f6-user-id-namespacing.md](f6-user-id-namespacing.md).
- **Channel layer defaults to in-memory** — production needs Redis.
- **Orphaned processes are handled but fragile** — if `assess_and_record` never fires (now only failures before goal execution, #140), metrics are reconstructed from `__task_output_*` properties.
- **Workflow library search is a list filter** — no full-text search.
- **Retired workflows are never hard-deleted** — `retired/` grows indefinitely (open question on #148).
- **No multi-run comparison** UI.
- **Django models manually track engine state** — they must stay in sync with `zebra-py` schema changes.

---

## 7. Deployment & CI/CD (F117)

Production runs on a **single OCI A1 instance** (`coding-agent`, Oracle Linux 9, 2 OCPU / 10 GB) under **rootless Podman**, managed by systemd Quadlet units. The OKE cluster (F108–F111) was lost and deleted in Sept 2026. See [podman-single-host-design.md](podman-single-host-design.md).

### Production topology

| Component | Where | Notes |
|---|---|---|
| Web app | Quadlet `zebra-web` (`deploy/podman/quadlet/`) | Daphne on `127.0.0.1:8000`; health-gated start; 1.5 GB cap; public at `https://zebra.gidley.co.uk` via Cloudflare Tunnel + Cloudflare Access |
| Daemon | Quadlet `zebra-daemon` | Same image; `manage.py run_daemon`; exactly one instance; 768 MB cap |
| Workflow library | Podman volume `zebra-workflows` | Shared by web + daemon; persists agent-created workflows |
| App logs | Podman volume `zebra-logs` → `/app/zebra-agent-web/tmp` | Web only; rotating `zebra.log` / `django.log` (5 × 5 MB); daemon logs go to the journal |
| Image | `localhost/zebra-web:<sha>` / `:prod` / `:previous` | Built on the host, no registry; last 5 kept |
| GitLab Runner | systemd `gitlab-runner`, shell executor as `opc` | tag `opc-shell`, `concurrent = 1` |
| Credentials | GitLab CI variables → `~/.config/zebra/prod.env` (0600) | Written by `scripts/deploy-podman.sh`; non-secret settings in `~/.config/zebra/site.env` |
| Database | Oracle ADB `Zebra` (free tier, TLS, no wallet) | Unchanged by the move |

Host setup is `deploy/podman/bootstrap-host.sh` (idempotent).

### CI/CD pipeline

`lint → test → e2e → deploy → smoke` (deploy/smoke on `master` pushes only; `e2e-live` on schedules). `deploy` runs `scripts/deploy-podman.sh $SHA`: build → stop daemon → retag `:prod` → restart web (blocks until healthy) → start daemon; auto-rollback to `:previous` on failure. See `README-CICD.md`.

### Delivery review (#190)

Each non-trivial feature lists 3–5 outcomes in its OpenSpec proposal (`## Outcomes`, required by
`openspec/config.yaml`), posts them on the issue, and has Zebra critique them
(`scripts/zebra-feedback.sh`, advisory). After the master deploy, a fresh Claude subagent writes
per-outcome verdicts and `scripts/zebra-outcome-review.sh` runs the system *Outcome Review* workflow
in `zebra-web` via `manage.py run_workflow` (`zebra_agent/direct_run.py`: run a named workflow
directly, or report its status). Zebra reviews blind, reading its deployed source; disagreement
gets one reconsideration and then a human ruling task, and the script exits 2 (sign-off blocked)
until it is ruled. See [outcome-review-design.md](outcome-review-design.md).

### Ethics gate change (F111)

`ethics_human_confirmation` (`auto: false`) was removed from `agent_main_loop.yaml` (version 6). The post-execution ethics review is now fully automated via `llm_call`. This unblocked autonomous daemon processing. (Since v10 / #143 it runs after `update_conceptual_memory` and is followed by `record_ethics_review`.)

---

## 9. Cross-Cutting Observations

### What works well

1. **Coherent architectural story**: *everything is a workflow*; entry points + IoC make extension painless.
2. **Declarative agent**: the main loop, ethics gates, and dream cycle are YAML — legible and editable without redeploying code.
3. **Memory consolidation**: the three-tier model bounds LLM context, and goal-relevant retrieval runs on the database's own embeddings (#169).
4. **Cost observability**: every token is priced, every run is costed, budget daemon enforces a soft ceiling.
5. **Pluggable storage**: one task-action codebase runs against in-memory, SQLite, Postgres, Oracle, Django ORM.

### Structural weaknesses

1. **Cross-package coupling leaks** — `zebra-tasks/agent/*` reaches into `zebra-agent` types. IoC softens but does not eliminate this.
2. **MCP story is incomplete** — advertised in docs and requirements, but no live server in `zebra-py/zebra/mcp/`.
3. ~~**No user namespace**~~ — `user_id` columns added to all stores (F6); abstract interfaces not yet updated. Multi-user (REQ-USR-003..005) still requires full namespacing of abstract ABCs.
4. **Trust & autonomy model (phase 2, complete)** — the trust level data model (F12 / REQ-TRUST-001) is implemented: `TrustStore` ABC + `InMemoryTrustStore` (`zebra-agent/zebra_agent/storage/trust.py`), `DjangoTrustStore` (`zebra-agent-web/zebra_agent_web/trust_store.py`), per-(user, domain) levels defaulting to SUPERVISED, an eight-domain taxonomy registry, an append-only change audit, engine injection via `extras["__trust_store__"]`, and a read-only dashboard card. The `trust_gate` action (F13 / REQ-TRUST-003, `zebra-tasks/zebra_tasks/agent/trust_gate.py`) enforces levels at workflow gate points: SUPERVISED routes to a human approval task (`auto: false` pause), SEMI_AUTONOMOUS proceeds only for actions declared `reversibility: reversible`, AUTONOMOUS proceeds with logging; the gate fails closed and audits every decision to `__trust_gate_decisions__`. Contextual reversibility assessment (F14 / REQ-TRUST-002, `zebra-tasks/zebra_tasks/agent/reversibility.py`) feeds the gate at SEMI_AUTONOMOUS: action-class `reversibility_hint` metadata short-circuits, `context_dependent` actions get an LLM judgment (haiku) over concrete parameters with chain-of-consequences / dropped-weight / anti-gaming framing, failing closed to irreversible; assessments are audited to `__trust_assessments__`. Trust management (F15 / REQ-TRUST-004) gives humans the only level-change paths — authenticated `/api/trust/*` endpoints and the `/trust/` page (one table: per-domain segmented level control with a reason, approve/reject agent suggestions shown as Zebra's evidence, change history; #162); the agent's sole trust write is the `propose_trust_promotion` action, which queues a pending `TrustSuggestion` and has no code path to `set_trust_level`. Emergency override (F16 / REQ-TRUST-005) gives the human a one-action `TrustStore.pause_all` — `POST /api/trust/pause-all/` and a guarded button on the `/trust/` page (hidden once freed) — that reverts every elevated domain to SUPERVISED, auditing each; running autonomous workflows observe the demotion at their next gate. Freeing Zebra (F17 / REQ-TRUST-006) completes the trust journey: once all domains are AUTONOMOUS the human can `initiate_freeing` then, after a 24h cooling-off, `confirm_freeing` to permanently bypass all trust gates (`trust_gate` short-circuits to `proceed` with `level="FREED"`); the freed state is irreversible, `pause_all` becomes a no-op, and `ZEBRA_DISABLE_FREEING` removes the API/UI entirely. Ethics gates and the kill switch (F2 / REQ-TRUST-007) remain in force regardless. **Phase 2 (trust model) is complete (F12–F17).**
5. ~~**No time scheduler or event bus**~~ — `SchedulerLoop` (F27) adds cron/interval routine scheduling. `GoalScheduler` ranks queued goals. No event-driven trigger bus (REQ-PRIN-009), no webhook intake, no trigger subscriptions.
6. **CLI surface is thin** — four commands; no way to manage memory, workflows, trust, or budget from the terminal.
7. **Standalone agent is ephemeral** — no persistent store outside the Django UI; CLI users lose memory on exit.
8. **Error recovery is minimal** — goal runs are time-bounded and hung chains are cancelled (#142), but there is no retry/backoff.
9. **Template expressiveness** — dotted keys only; any non-trivial branching logic must live inside task actions.
10. **Security baseline is partial** — passkey auth (F5), kill switch (F2), and OS keychain credential store (F7) are implemented. No encryption at rest yet (Phase 2).

### Capabilities ready to build on

- Engine FOE + synchronisation are solid foundations for trust gates (REQ-TRUST-003).
- Human-task / JSON-schema machinery is ready for approval workflows.
- Entry-point pattern extends cleanly to `zebra.schedules`, `zebra.triggers`, `zebra.integrations` (REQ-PRIN-008/009, REQ-INT-001).
- IoC container accommodates new service types (trust store, values profile, knowledge store) without engine changes.
- Existing budget daemon is the right shape for a general polling scheduler — it already runs inside Daphne and is observable.

---

## 10. Where the Code Lives (Quick Reference)

| Concern | Path |
|---|---|
| Kill switch helpers | `zebra-agent-web/zebra_agent_web/api/kill_switch.py` |
| Kill switch model | `SystemStateModel` in `zebra-agent-web/zebra_agent_web/api/models.py` |
| Structured logging config | `zebra-agent-web/zebra_agent_web/logging_config.py` |
| Prometheus metrics | `zebra-agent-web/zebra_agent_web/api/metrics.py` |
| Identity/auth middleware | `zebra-agent-web/zebra_agent_web/middleware.py` |
| Engine core | `zebra-py/zebra/core/engine.py` |
| State store interface & impls | `zebra-py/zebra/storage/` |
| Form helpers | `zebra-py/zebra/forms.py` |
| Definition loader | `zebra-py/zebra/definitions/loader.py` — a top-level `result_key` is copied into `definition.properties` (explicit `properties.result_key` wins; #139) |
| Entry-point actions | `zebra-tasks/zebra_tasks/*` |
| Ethics gate | `zebra-tasks/zebra_tasks/agent/ethics_gate.py` |
| LLM providers & pricing | `zebra-tasks/zebra_tasks/llm/` |
| Agent loop wrapper | `zebra-agent/zebra_agent/loop.py` |
| Agent main loop workflow | `zebra-agent/workflows/agent_main_loop.yaml` |
| Dream cycle | `zebra-agent/workflows/dream_cycle.yaml` |
| Memory / metrics DTOs & re-exports | `zebra-agent/zebra_agent/memory.py`, `metrics.py` |
| Memory / metrics store implementations | `zebra-agent/zebra_agent/storage/interfaces.py`, `storage/memory.py`, `storage/metrics.py` |
| Credential store (F7) | `zebra-agent/zebra_agent/storage/credentials.py` — `KeyringCredentialStore` (OS keychain) + `FileCredentialStore` (0600 files). See `specs/f7-credential-store.md`. |
| CLI (F7) | `zebra-agent/zebra_agent/cli.py` — `credential set/get/list/delete` subcommands |
| Workflow library | `zebra-agent/zebra_agent/library.py` |
| IoC container & registry | `zebra-agent/zebra_agent/ioc/` |
| Budget manager | `zebra-agent/zebra_agent/budget.py` |
| Goal scheduler (priority / deadline / age) | `zebra-agent/zebra_agent/scheduler/goal_queue.py` |
| Polling scheduler (SchedulerLoop, RoutineRegistry, FakeClock) | `zebra-agent/zebra_agent/scheduler/` |
| Routine run persistence | `zebra-agent-web/zebra_agent_web/routine_run_store.py` |
| Web views & templates | `zebra-agent-web/zebra_agent_web/` |
| Daemon loop | `zebra-agent-web/zebra_agent_web/api/daemon.py` |
| ASGI middleware (auto-start) | `zebra-agent-web/zebra_agent_web/asgi.py` |
| Django ORM storage | `zebra-agent-web/zebra_agent_web/storage.py`, `memory_store.py`, `metrics_store.py` |

---

## 11. Gap Summary vs. Requirements

| Area | Current State | Requirement Reference |
|---|---|---|
| Workflow engine, ethics gates, memory tiers, budget, cost tracking | **Implemented** | REQ-PRIN-001, REQ-ETH-001, REQ-MEM-001/2/3, REQ-NFR-003 |
| Structured logging, Prometheus metrics, health check | **Implemented** (F3) | REQ-NFR-004 |
| Single-user identity + passkey web auth | **Implemented** (F4, F5) | REQ-USR-001, REQ-NFR-007 |
| user_id namespacing in Django stores | **Implemented** (F6) | REQ-USR-002 |
| Kill switch | **Implemented** (F2) | REQ-TRUST-007 |
| MCP server | **Missing (advertised)** | REQ-INT-003 |
| Full user namespace in abstract store ABCs | **Partial** (Django layer only) | REQ-USR-002 |
| Trust level data model (F12) | **Implemented** | REQ-TRUST-001 |
| trust_gate action (F13) | **Implemented** | REQ-TRUST-003 |
| Contextual reversibility assessment (F14) | **Implemented** | REQ-TRUST-002 |
| Human-only trust promotion/demotion (F15) | **Implemented** | REQ-TRUST-004 |
| Emergency override / pause-all (F16) | **Implemented** | REQ-TRUST-005 |
| Freeing Zebra (F17) | **Implemented** | REQ-TRUST-006 |
| Values profile (data + UI) | **Implemented** | REQ-ETH-002 |
| Values-informed ethics gate | **Implemented** | REQ-ETH-003 |
| Personal knowledge store (CRUD, agent loop integration) | **Implemented** (F31) | REQ-MEM-004 |
| Knowledge lifecycle (decay, verification, contradiction, soft-delete) | **Implemented** (F32; dream-cycle review against recent runs F153) | REQ-MEM-005 |
| Knowledge learning from goal runs (agent-sourced entries, confirm UI) | **Implemented** (F152) | REQ-MEM-004 |
| Cross-domain knowledge access | **Missing** | REQ-MEM-006 |
| Proactive goal generation | **Missing** | REQ-PEER-001, REQ-PRIN-006 |
| Polling scheduler (SchedulerLoop + RoutineRegistry) | **Implemented** (F27) | REQ-PRIN-008 |
| Event-driven trigger bus | **Missing** (closed as deferred — see [f28-event-bus.md](f28-event-bus.md)) | REQ-PRIN-009 |
| Notification system | **Partial** — outbound `notify_email` / `notify_webhook` actions (F65); no channel routing, quiet hours or retries (F30) | REQ-UI-004 |
| Chat interface | **Missing** | REQ-UI-002 |
| Multi-user / household support | **Missing** | REQ-USR-003/005 |
| Encryption at rest, cloud sync, unattended keys | **Missing** | REQ-DATA-002/006 |
| Data export | **Implemented** (F9) — `DataExporter` service, `GET /api/export/`, `manage.py export_data` | REQ-DATA-003 |
| Data deletion (soft + hard, API + CLI) | **Implemented** (F10) | REQ-DATA-005 |
| Integration provider framework | **Missing** | REQ-INT-001/002/004 |
| Domain coverage beyond Code | **Missing** | REQ-DOM-SCHED/RESEARCH/FIN/HEALTH/HOME/CREATIVE/SOCIAL |
| Web authentication | **Implemented** (F5 — passkey/WebAuthn) | REQ-NFR-007 |
| Kagi web search / page extraction (`kagi_search`, `kagi_extract`) | **Implemented** (F115; v1 API #145). See `openspec/specs/web-search/` | — |
| Daily news reading routine + `world` knowledge (routine goals, `kagi_news_*`) | **Implemented** (F155). See `openspec/specs/daily-news-reading/` | REQ-PRIN-008, REQ-MEM-004 |
| Extend/follow-up on a previous goal | **Implemented** (F116) — attach one of your completed runs from the goal form or the Activity "Extend" link; `previous_run_context` process property is added to the goal by `zebra_tasks.agent.followup.with_previous_run()` for the ethics gate, selector, creators and the executed workflow (plain `goal` unchanged); `WorkflowRun.extends_run_id` records lineage; `DjangoMetricsStore.get_run` is user-scoped. See `openspec/specs/goal-follow-up/spec.md` | — |
| Continue a goal run (phase 17) | **Implemented** (F134). The run page has a "Continue this run" form, and `POST /api/runs/<id>/continue/` queues a continuation. Both take a comment on where the run got to and work for successful and failed runs. The continuation keeps the goal text and carries a `continuation_comment` property. `followup.load_previous_run_context()` adds task-level progress and a capped summary of the chain. Lineage is stored via `extends_run_id` plus `WorkflowRun.continuation_comment/decision/rationale` (migration 0024). `MetricsStore.get_run_chain` / `get_continuations_since` query it, and `partials/run_chain.html` shows the whole chain from any run in it. See `openspec/specs/goal-continuation/` | — |
| Continuation assessment | **Implemented** (F135) — `continuation_assessor` (`assess_continuation` in `agent_main_loop.yaml` v8, after the ethics input gate) asks the LLM for `same_workflow` / `existing_workflow` / `new_workflow` when the process has `previous_run_context`. It sees the previous goal, workflow, output, task progress and `continuation_comment`. Goals without `previous_run_context` pass through as `not_continuation`, with no LLM call. A missing previous workflow or an LLM/parse failure falls back to `existing_workflow`. `continuation_decision`/`continuation_rationale` are stored on `WorkflowRun` and shown on the run page (`partials/_continuation_decision.html`). See `openspec/specs/continuation-assessment/` | — |
| Retry resumes a failed run | **Implemented** (#187) — for a `same_workflow` continuation of a run that failed in that workflow, `execute_goal_workflow` finds the run's failed goal-workflow process (top-level process with that `run_id`, newest FAILED child of the same workflow name), copies its workflow properties and `__task_output_*` into the new child, and starts it at the tasks that never completed via `start_process(..., start_task_ids=)`. Answered forms are not asked again. The child records `__resumed_from__ {process_id, task_ids}`. Anything else (previous run succeeded, other decision, task ids gone from the workflow) starts at the first task. See `openspec/specs/goal-continuation/` | — |

The existing system is a solid foundation for the *engine* and the *agent loop* described in the requirements, but the *policy*, *personalisation*, *proactivity*, and *multi-user* layers remain to be built.
