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

- **Process lifecycle**: `CREATED → RUNNING → COMPLETE` (with `PAUSED`, `FAILED`).
- **Task lifecycle**: `PENDING → AWAITING_SYNC → READY → RUNNING → COMPLETE` / `FAILED`.
- **Flow of Execution (FOE)**: tracks parallel branches. Serial routings inherit the parent FOE; parallel routings fork new FOEs. Synchronised (`synchronized: true`) tasks wait for all incoming FOEs via backward-reachability.

### Routing

- Implicit serial/parallel edges declared in YAML.
- Conditional routing via `TaskResult.ok(output=..., next_route="name")` matching a `routings[].name` entry. Used by ethics gates, workflow selection, memory checks.
- Built-in conditions: `AlwaysTrueCondition`, `RouteNameCondition` — anything else requires a registered custom condition.

### Storage

- `StateStore` abstract interface covers definitions, instances, FOEs, locking.
- Implementations: `InMemoryStore` (tests), `SQLiteStore`, `PostgresStore`.
- **JSON-serialisation is enforced at the Pydantic layer** — non-serialisable objects cannot be placed in process properties. Services pass through `engine.extras` instead (the IoC escape hatch).

### Definition model

- `ProcessDefinition` / `TaskDefinition` are **frozen** Pydantic models. YAML or JSON loaders produce them.
- Template resolution is regex-based: `{{var}}` and `{{task_id.output.key}}`. No arithmetic, no conditionals, no loops inside templates.

### Human tasks & forms

- Convention-based: `auto: false` + a JSON Schema under `properties.schema`. No action runs; the task sits `READY` until externally completed.
- `zebra.forms` converts JSON Schema to a `FormSchema` (list of `FormField`), with `coerce_form_data` and `validate_form_data` helpers. Enum fields can drive named routes (e.g., approve / reject).

### Strengths

- Clean separation of definition (immutable) vs. instance (mutable).
- Fully async; storage and actions are pluggable.
- Serialisation contract catches bad property writes early.
- FOE model handles arbitrary fork/join topologies.

### Weaknesses / gaps

- **MCP server advertised in the README but not present** in `zebra-py/zebra/mcp/` — the requirements spec (Appendix B) references this path, but no code lives there today.
- **Template language is weak** — no expressions beyond dotted key lookup.
- **No retry / backoff** in the engine. An `execution_attempts` counter exists but no recovery policy.
- **Postgres backend is thinner than SQLite** — less test coverage, feature-completeness unclear.

---

## 4. Task Actions (`zebra-tasks`)

### Catalogue

| Category | Actions |
|---|---|
| LLM | `llm_call` |
| Subtasks | `subworkflow`, `wait_subworkflow`, `parallel_subworkflows` |
| Filesystem | `file_read`, `file_write`, `file_copy`, `file_move`, `file_delete`, `file_search`, `file_exists`, `file_info` (9 actions) |
| Compute | `python_exec` (sandboxed) |
| Agent loop | `consult_memory`, `workflow_selector`, `workflow_creator`, `workflow_variant_creator`, `execute_goal_workflow`, `assess_and_record`, `update_conceptual_memory`, `record_metrics`, `load_workflow_definitions`, `queue_goal` |
| Dream cycle | `metrics_analyzer`, `workflow_evaluator`, `workflow_optimizer` |
| Ethics | `ethics_gate` |

### LLM integration

- Provider abstraction supports **Anthropic Claude** (primary) and **OpenAI**, registered lazily via a factory registry.
- Pricing table hardcoded in `pricing.py` (per-1M-token Anthropic rates); Sonnet defaults for unknowns.
- Every call updates process properties: `__total_cost__`, `__total_tokens__`, `__token_history__`.
- Soft budget warnings via an injected `__budget_manager__` (non-blocking).

### Registration

- Entry points in `pyproject.toml` under `[project.entry-points."zebra.tasks"]` — loaded by `importlib.metadata` at startup. No imperative registration required.

### Weaknesses

- **Agent actions are coupled to `zebra-agent`** (import its memory / library / metrics types). Soft-decoupled via `context.extras`, but still a layering leak.
- **Subtasks don't roll up cost** — child `__total_cost__` isn't propagated into the parent automatically for all paths. (The web daemon does its own propagation in `assess_and_record`.)
- **Ethics gate is advisory** — it only evaluates; workflows must explicitly route on its output to block.
- **No structured-output guarantees** on LLM calls — JSON is extracted post-hoc by regex.
- **Filesystem actions have minimal sandboxing** — path sanitisation only; no whitelist.

---

## 5. Agent Library (`zebra-agent`)

### Agent main loop (declarative)

The loop lives in `workflows/agent_main_loop.yaml`, not Python. `AgentLoop` is a ~200-line wrapper that starts the workflow and awaits it. The loop:

```
consult_memory
  → ethics_input_gate
  → workflow_selector
  → [create_new | create_variant | use_existing]
  → ethics_plan_review
  → execute_goal_workflow
  → ethics_post_review
  → assess_and_record
  → update_conceptual_memory
```

### Dream cycle (`dream_cycle.yaml`)

Self-improvement loop: `metrics_analyzer` → `workflow_evaluator` → `workflow_optimizer`. Runs over the last N days of metrics; can propose edits to stored workflows.

### Memory

Three-tier model (matches the design in REQ-DATA-004):

| Tier | Interface | Implementations | Typical size |
|---|---|---|---|
| Working (process properties) | `ExecutionContext` | in-engine | unbounded per run |
| Episodic (`WorkflowMemoryEntry`) | `MemoryStore` | `InMemoryMemoryStore`, `DjangoMemoryStore` | last 5 / workflow |
| Conceptual (`ConceptualMemoryEntry`) | `MemoryStore` | same | ≤50 entries into LLM |

### Metrics

`MetricsStore` records workflow runs, task executions, tokens, USD cost, and user ratings. Two implementations (in-memory, Django). `get_total_cost_since()` feeds the budget manager.

### Workflow library

`WorkflowLibrary` loads YAMLs from `~/.zebra-agent/workflows/`, caches them, flags system workflows (main loop, dream, create_goal), tracks success rate and use count.

### Budget

`BudgetManager` enforces daily USD limits with linear time-of-day pacing (`allowed = daily * hours_elapsed / 24`). Soft warnings only; no hard block mid-run. Stateless — it reads live from `MetricsStore`.

### IoC

`ZebraContainer` (dependency-injector) plus `IoCActionRegistry` inspect action `__init__` signatures and inject services automatically. Entry-point discovery makes adding a new action zero-config.

### CLI

Minimal: `/list`, `/stats`, `/help`, `/quit`. Launch with `zebra-agent` / `python -m zebra_agent.cli`. No trust, values, knowledge, or budget commands yet.

### Ethics gates

Three checkpoints wired into `agent_main_loop.yaml`: input gate, plan review, post-execution review. Implementation is LLM-prompt-based Kantian reasoning (universalizability, rational beings as ends, autonomy). Human confirmation task waits for acknowledgement before completion.

`EthicsGateAction` accepts an optional `user_id` input. When provided and `__profile_store__` is available in `context.extras`, the gate loads the user's current `ValuesProfile` and incorporates it into a combined evaluation prompt. Kantian rejection always takes precedence (values can only restrict further). The stored assessment includes a `values_assessment` key (`null` for Kantian-only runs). Verdict log lines show both Kantian and values flags when a profile was consulted.

### Values profile (F18 / REQ-ETH-002)

Per-user profile of `core_values`, `ethical_positions`, `priorities`, and `deal_breakers` — free-form text plus structured tags. The data lives behind a new `ProfileStore` interface (`zebra_agent/storage/interfaces.py`) with `InMemoryProfileStore` and `DjangoProfileStore` backends.

- **Versioning.** Every save creates an immutable `ValuesProfileVersion` with a monotonic `version_number`; `ValuesProfileModel.current_version` points to the latest. Old versions are retained for audit.
- **Hybrid taxonomy.** Tags are field-scoped with `status ∈ {seeded, promoted, candidate}`. The wizard's extract step asks an LLM to pick from the approved set (`seeded + promoted`) and propose new candidates from free-form text. User-confirmed candidates are persisted as `candidate` rows with incremented `usage_count`. Promotion of candidates → `promoted` is deferred to a follow-up issue (out of F18 scope).
- **Wizard.** `zebra-agent/workflows/values_profile_wizard.yaml` is a system workflow with eight steps: load existing profile (auto), four free-form text forms (human tasks), extract tags via LLM (auto), review (human task), save (auto). Used for both first-time capture and edit mode (signalled by `existing_profile_version_id` in the initial process properties; load step pre-populates form defaults).
- **Bootstrap.** `manage.py bootstrap_values_taxonomy` calls an LLM to draft a starter taxonomy and writes a reviewable YAML fixture; the maintainer reviews and commits it, and a data migration loads it as `status="seeded"` on first `migrate`.
- **Web entry-point.** `/profile/values/` (`web_views.values_profile_wizard`) creates a wizard process for the authenticated user and redirects to the first pending task.
- **Wired into the ethics gate (F19).** `EthicsGateAction` reads the profile via `ProfileStore.get_current()` when `user_id` is supplied. Kantian precedence rule applied in Python.

### Strengths

- Declarative agent behaviour — YAML is editable, inspectable, version-controllable.
- Pluggable storage cleanly decouples task actions from database choice.
- Memory consolidation keeps LLM context bounded without RAG infrastructure.
- Cost tracking is fine-grained and surfaced.

### Weaknesses

- **Standalone CLI loses all state on exit** — no SQLite default; only in-memory stores.
- **Dream cycle is experimentally powerful but unvalidated** — LLM-driven mutations aren't gated by tests.
- **No trust model exists.** Requirements describe SUPERVISED / SEMI-AUTONOMOUS / AUTONOMOUS; implementation has none of this.
- ~~**No values profile** — ethics is generic Kantian, not personalised.~~ Resolved by F18 (data + UI) and F19 (ethics-gate consumption, REQ-ETH-003).
- ~~**No personal knowledge store** — only the three workflow-focused tiers.~~ Resolved by F31 (store, CRUD UI, agent loop integration) and F32 (lifecycle: decay, verification, contradiction detection, soft-delete).
- ~~**Only a goal scheduler, not a time/event scheduler**~~ — `GoalScheduler` (`zebra-agent/zebra_agent/scheduler/goal_queue.py`) picks the next CREATED process for the budget daemon. A cron/interval `SchedulerLoop` now fires built-in and user-defined routines (F27 / REQ-PRIN-008). There is **no event-driven trigger bus** (REQ-PRIN-009).
- ~~**Single-user implicit** — no `user_id` namespacing anywhere in stores or schemas.~~ Resolved by F6 (REQ-USR-002).
- **Agent main loop YAML is 258 lines** — hard to unit-test sub-branches.
- **Conceptual memory scan is O(n)** — no indexing; fine for hundreds of entries, degrades thereafter.

---

## 6. Web UI (`zebra-agent-web`)

### Stack

- **Django 5 + Daphne + Channels**
- **HTMX 2 + Alpine.js 3 + Tailwind (CDN)** — no frontend build step
- **Django REST Framework** for JSON endpoints

### Routes

| Path | Purpose |
|---|---|
| `/` | Dashboard: budget, workflow count, success rate |
| `/run/` | Goal submission (priority, deadline, queue, model) |
| `/activity/` | Recent runs (handles orphaned processes) |
| `/runs/<id>/` | Run detail with SVG workflow diagram |
| `/workflows/` | Library browser |
| `/tasks/` & `/tasks/<id>/` | Pending human tasks + JSON-Schema form |
| `/api/runs/<id>/diagram/` | SVG |
| `/api/tasks/<id>/complete/` | Submit human task |
| `/api/budget/` | Budget status |
| `/ws/goal/<run_id>/` | Live progress WebSocket |

### Daemon

`DaemonStarterMiddleware` spawns `run_daemon_loop()` via `asyncio.create_task()` on the first request (Daphne doesn't run ASGI lifespan events). Loop: `pick_next → budget_check → start_process → poll → record metrics → repeat`. Also runnable via `python manage.py run_daemon`.

### Storage backends (Django ORM)

- `DjangoStore` (workflow state — `ProcessInstanceModel`, `TaskInstanceModel`, `FlowOfExecutionModel`)
- `DjangoMemoryStore`, `DjangoMetricsStore`
- Works against SQLite, PostgreSQL, Oracle (Oracle is the integration-test target).

### Forms

Server-side: reuses `zebra.forms` (`schema_to_form` + coerce/validate).
Template tag `{% render_schema_form %}` renders Tailwind-styled fields with per-field errors, required markers, route buttons.

### Kill switch (F2)

`POST /api/kill-switch/` sets a persisted `halted` flag in `SystemStateModel`. The daemon checks this flag before each goal pickup and during polling — in-flight processes are failed within 2 s of activation. `python manage.py kill_switch --halt|--resume|--status` is the CLI equivalent. See [f2-kill-switch.md](f2-kill-switch.md).

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
- See [f4-f5-identity-auth.md](f4-f5-identity-auth.md) for full detail.

### Weaknesses

- **No passkey management UI** — users cannot delete or rename registered passkeys.
- **No per-user isolation in all paths** — `clear_conceptual_memories` wipes all users (latent bug). See [f6-user-id-namespacing.md](f6-user-id-namespacing.md).
- **Channel layer defaults to in-memory** — production needs Redis.
- **Orphaned processes are handled but fragile** — if `assess_and_record` never fires, metrics are reconstructed from `__task_output_*` properties.
- **Workflow library search is a list filter** — no full-text, no tagging.
- **No multi-run comparison** UI.
- **Django models manually track engine state** — they must stay in sync with `zebra-py` schema changes.

---

## 7. Cross-Cutting Observations

### What works well

1. **Coherent architectural story**: *everything is a workflow*; entry points + IoC make extension painless.
2. **Declarative agent**: the main loop, ethics gates, and dream cycle are YAML — legible and editable without redeploying code.
3. **Memory consolidation**: the three-tier model bounds LLM context without embeddings or vector DBs.
4. **Cost observability**: every token is priced, every run is costed, budget daemon enforces a soft ceiling.
5. **Pluggable storage**: one task-action codebase runs against in-memory, SQLite, Postgres, Oracle, Django ORM.

### Structural weaknesses

1. **Cross-package coupling leaks** — `zebra-tasks/agent/*` reaches into `zebra-agent` types. IoC softens but does not eliminate this.
2. **MCP story is incomplete** — advertised in docs and requirements, but no live server in `zebra-py/zebra/mcp/`.
3. ~~**No user namespace**~~ — `user_id` columns added to all stores (F6); abstract interfaces not yet updated. Multi-user (REQ-USR-003..005) still requires full namespacing of abstract ABCs.
4. **No trust model** — the policy layer required by REQ-TRUST-001..006 does not exist. The kill switch (F2 / REQ-TRUST-007) is implemented; ethics gates are values-informed but advisory. Full `TrustStore` + `trust_gate` action is pending (F12-F17).
5. ~~**No time scheduler or event bus**~~ — `SchedulerLoop` (F27) adds cron/interval routine scheduling. `GoalScheduler` ranks queued goals. No event-driven trigger bus (REQ-PRIN-009), no webhook intake, no trigger subscriptions.
6. **CLI surface is thin** — four commands; no way to manage memory, workflows, trust, or budget from the terminal.
7. **Standalone agent is ephemeral** — no persistent store outside the Django UI; CLI users lose memory on exit.
8. **Error recovery is minimal** — timeouts, but no retry/backoff, no hung-call detection.
9. **Template expressiveness** — dotted keys only; any non-trivial branching logic must live inside task actions.
10. **Security baseline is partial** — passkey auth (F5), kill switch (F2), and OS keychain credential store (F7) are implemented. No encryption at rest yet (Phase 2).

### Capabilities ready to build on

- Engine FOE + synchronisation are solid foundations for trust gates (REQ-TRUST-003).
- Human-task / JSON-schema machinery is ready for approval workflows.
- Entry-point pattern extends cleanly to `zebra.schedules`, `zebra.triggers`, `zebra.integrations` (REQ-PRIN-008/009, REQ-INT-001).
- IoC container accommodates new service types (trust store, values profile, knowledge store) without engine changes.
- Existing budget daemon is the right shape for a general polling scheduler — it already runs inside Daphne and is observable.

---

## 8. Where the Code Lives (Quick Reference)

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
| Definition loader | `zebra-py/zebra/definitions/loader.py` |
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

## 9. Gap Summary vs. Requirements

| Area | Current State | Requirement Reference |
|---|---|---|
| Workflow engine, ethics gates, memory tiers, budget, cost tracking | **Implemented** | REQ-PRIN-001, REQ-ETH-001, REQ-MEM-001/2/3, REQ-NFR-003 |
| Structured logging, Prometheus metrics, health check | **Implemented** (F3) | REQ-NFR-004 |
| Single-user identity + passkey web auth | **Implemented** (F4, F5) | REQ-USR-001, REQ-NFR-007 |
| user_id namespacing in Django stores | **Implemented** (F6) | REQ-USR-002 |
| Kill switch | **Implemented** (F2) | REQ-TRUST-007 |
| MCP server | **Missing (advertised)** | REQ-INT-003 |
| Full user namespace in abstract store ABCs | **Partial** (Django layer only) | REQ-USR-002 |
| Trust levels & trust gates (F12–F17) | **Missing** | REQ-TRUST-001..006 |
| Values profile (data + UI) | **Implemented** | REQ-ETH-002 |
| Values-informed ethics gate | **Implemented** | REQ-ETH-003 |
| Personal knowledge store (CRUD, agent loop integration) | **Implemented** (F31) | REQ-MEM-004 |
| Knowledge lifecycle (decay, verification, contradiction, soft-delete) | **Implemented** (F32) | REQ-MEM-005 |
| Cross-domain knowledge access | **Missing** | REQ-MEM-006 |
| Proactive goal generation | **Missing** | REQ-PEER-001, REQ-PRIN-006 |
| Polling scheduler (SchedulerLoop + RoutineRegistry) | **Implemented** (F27) | REQ-PRIN-008 |
| Event-driven trigger bus | **Missing** (closed as deferred — see [f28-event-bus.md](f28-event-bus.md)) | REQ-PRIN-009 |
| Notification system | **Missing** | REQ-UI-004 |
| Chat interface | **Missing** | REQ-UI-002 |
| Multi-user / household support | **Missing** | REQ-USR-003/005 |
| Encryption at rest, cloud sync, unattended keys | **Missing** | REQ-DATA-002/006 |
| Data export | Implemented — `DataExporter` service, `GET /api/export/`, `manage.py export_data`. See [specs/f9-data-export.md](f9-data-export.md). | REQ-DATA-003 |
| Integration provider framework | **Missing** | REQ-INT-001/002/004 |
| Domain coverage beyond Code | **Missing** | REQ-DOM-SCHED/RESEARCH/FIN/HEALTH/HOME/CREATIVE/SOCIAL |
| Web authentication | **Implemented** (F5 — passkey/WebAuthn) | REQ-NFR-007 |

The existing system is a solid foundation for the *engine* and the *agent loop* described in the requirements, but the *policy*, *personalisation*, *proactivity*, and *multi-user* layers remain to be built.
