# Zebra — To-Be Technical Design

**Date**: 2026-04-17
**Status**: Draft for review
**Companions**:
- [../docs/requirements.md](../docs/requirements.md) — target requirements (REQ-* IDs referenced throughout).
- [zebra-as-is.md](zebra-as-is.md) — current implementation snapshot.

This document is the **high-level technical design** that bridges as-is to target. It describes *what components exist, how they fit together, and what interfaces they expose* — not line-level implementation detail.

---

## 1. Design Principles

All new components respect the existing architectural grain:

1. **Everything is a workflow** (REQ-PRIN-001) — new capabilities are new task actions + YAML, not new imperative code paths.
2. **Plug-ins via entry points** (REQ-PRIN-002) — new subsystems (schedules, triggers, integrations, notifications, domains) register via `zebra.*` entry-point groups; `IoCActionRegistry`-style discovery does the rest.
3. **Abstract storage** — every new store defines an interface in `zebra-agent/zebra_agent/storage/interfaces.py` (or a new equivalent module) with at least an in-memory and a Django implementation.
4. **Services via `engine.extras`** — non-serialisable dependencies travel through IoC, never through process properties.
5. **Local-first** (REQ-PRIN-005) — every persistent component has a local-only default; sync is opt-in.
6. **User-scoped from day one** (REQ-USR-002) — every new interface takes a `user_id`, even when the deployment is single-tenant.
7. **Trust is enforced at gates, not in actions** — task actions remain domain-focused; policy is layered above them.

---

## 2. Target Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│ Interface Surface                                                    │
│   Web Dashboard • Chat • CLI • Notifications • MCP Server • Webhooks │
└──────────────────────────────────────────────────────────────────────┘
                    ▲                           ▲
                    │                           │
┌────────────────────────────┐   ┌───────────────────────────────────┐
│ Proactivity                │   │ Policy & Identity                 │
│   Scheduler (cron routines)│   │   UserContext / IdentityStore     │
│   Event Bus (triggers)     │   │   TrustStore + trust_gate action  │
│   Budget Daemon (existing) │   │   ValuesProfile + ethics extension│
└────────────────────────────┘   └───────────────────────────────────┘
                    ▲                           ▲
                    └──────────────┬────────────┘
                                   │
┌──────────────────────────────────────────────────────────────────────┐
│ Agent Loop (declarative YAML — extended)                             │
│   consult_memory → ethics_input_gate → trust_gate → select → …       │
└──────────────────────────────────────────────────────────────────────┘
                                   ▲
┌──────────────────────────────────────────────────────────────────────┐
│ Memory & Knowledge                                                   │
│   Working • Episodic • Conceptual (existing)                         │
│   + PersonalKnowledgeStore (new)                                     │
│   + RelationshipMemory (new, thin layer over episodic)               │
└──────────────────────────────────────────────────────────────────────┘
                                   ▲
┌──────────────────────────────────────────────────────────────────────┐
│ Task Actions (entry points)                                          │
│   zebra.tasks  — existing + trust_gate, retrieve_knowledge, …        │
│   zebra.conditions                                                   │
│   zebra.schedules (new)                                              │
│   zebra.triggers (new)                                               │
│   zebra.integrations (new)                                           │
│   zebra.notifications (new)                                          │
│   zebra.domains (new — groups actions + workflows)                   │
└──────────────────────────────────────────────────────────────────────┘
                                   ▲
┌──────────────────────────────────────────────────────────────────────┐
│ Core Engine (zebra-py) — unchanged public surface                    │
│   WorkflowEngine • StateStore • FOE • Forms • Templates              │
└──────────────────────────────────────────────────────────────────────┘
                                   ▲
┌──────────────────────────────────────────────────────────────────────┐
│ Security & Data Layer                                                │
│   Credential Store (OS keychain) • DEK/KEK envelope encryption       │
│   Per-user namespaces • Data export • Soft/hard delete • Audit log   │
└──────────────────────────────────────────────────────────────────────┘
```

Green-field subsystems are: **UserContext**, **TrustStore**, **ValuesProfile**, **PersonalKnowledgeStore**, **Scheduler**, **EventBus**, **IntegrationProvider**, **NotificationChannel**, **CredentialStore**, **MCP server**, **Chat**. Everything else is a preservation or extension of what already exists.

---

## 3. Identity & User Namespace (REQ-USR-001/002)

### `UserContext`

A lightweight dataclass carried through every request and workflow:

```
UserContext(
    user_id: str,             # stable UUID or configured slug
    display_name: str,
    roles: set[str],          # future RBAC hook (REQ-USR-004)
    household_id: str | None, # for Phase 3 multi-user (REQ-USR-003)
)
```

Propagation:

- **Interfaces** (web, chat, CLI, MCP) construct the `UserContext` at entry and inject it into every goal submission.
- **WorkflowEngine** receives it via `engine.extras["__user__"]` when starting a process, and stamps `process.properties["__user_id__"]` at creation.
- **Stores** accept `user_id` on every read/write. Single-user deployments use a default ID; the API never becomes optional.

### `IdentityStore`

New ABC: `list_users`, `get_user`, `create_user`, `update_user`, `delete_user`. Backed by:

- `InMemoryIdentityStore` (CLI default; single default user bootstrapped at init).
- `DjangoIdentityStore` (web, persisted).

Every existing store interface (`MemoryStore`, `MetricsStore`, `StateStore`) gains a mandatory `user_id` parameter on read/write methods. Migration plan: add parameter with default (`"default"`) first, then remove the default in a follow-up once all callers are updated.

---

## 4. Trust & Autonomy Layer (REQ-TRUST-001..007)

### `TrustStore`

```
TrustLevel = Enum("SUPERVISED", "SEMI_AUTONOMOUS", "AUTONOMOUS")
TrustStore:
  get_trust_level(user_id, domain) -> TrustLevel
  set_trust_level(user_id, domain, level, reason, changed_by) -> TrustChangeRecord
  list_trust_changes(user_id, domain=None) -> list[TrustChangeRecord]
  is_freed(user_id) -> bool          # REQ-TRUST-006
  freed_at(user_id) -> datetime | None
  pause_all(user_id, reason)         # REQ-TRUST-005
```

All domains default to `SUPERVISED` on first use. Trust changes are append-only for audit.

### `trust_gate` task action

Embedded in workflows that perform domain-scoped actions:

```yaml
check_trust:
  action: trust_gate
  properties:
    domain: "code"
    action_descriptor: "{{planned_action}}"
routings:
  - {from: check_trust, to: execute_action, condition: route_name, name: "proceed"}
  - {from: check_trust, to: request_approval, condition: route_name, name: "approve"}
  - {from: check_trust, to: blocked, condition: route_name, name: "block"}
```

Logic:

- `SUPERVISED` → always routes to `approve` (creates a human task).
- `SEMI_AUTONOMOUS` → evaluates reversibility; reversible → `proceed`, irreversible → `approve`.
- `AUTONOMOUS` / freed → `proceed` and logs.
- Kill switch trumps everything (see §11).

### Reversibility assessment (REQ-TRUST-002)

Each `TaskAction` class declares a `reversibility_hint: Literal["always_reversible", "always_irreversible", "context_dependent"]` (default `context_dependent`). The trust gate invokes:

```
assess_reversibility(task, context) -> ReversibilityAssessment(
    reversible: bool,
    reasoning: str,
    confidence: float,
    chain_notes: str,   # explicit note on downstream consequences
)
```

For `context_dependent` actions the assessment is an LLM call framed around:

1. The concrete parameters (what file, what endpoint, what recipient).
2. The *chain* of consequences — does this create conditions for later irreversible harm?
3. The Asimov "dropped weight" test — would absence of a later corrective step cause harm?

The assessment is stored in `process.properties["__trust_assessments__"]` for audit.

### Emergency override & kill switch

- **Pause all** (REQ-TRUST-005): `TrustStore.pause_all(user_id)` sets every domain to SUPERVISED. Running workflows observe the change at the next `trust_gate`.
- **Kill switch** (REQ-TRUST-007): a privileged `POST /kill` endpoint (separate token) and a matching CLI command call `EngineSupervisor.halt_all()`, which cancels all asyncio tasks and flips a `__kill_switch_triggered__` flag persisted to disk. On next start the flag is surfaced as an audit event. The kill switch is independent of trust and cannot be disabled from within the agent.

### Freeing Zebra (REQ-TRUST-006)

A one-time, multi-step confirmation flow (web + CLI) sets `IdentityStore.set_freed(user_id)`. `trust_gate` short-circuits to `proceed` when `is_freed(user_id)` is true. Ethics gates continue to run; only approval gates are bypassed. A compile-time feature flag (`ZEBRA_DISABLE_FREEING=true`) removes the UI and API endpoint entirely for deployments that must never allow it.

---

## 5. Values-Aligned Ethics (REQ-ETH-001..006)

### `ValuesProfile`

Versioned, user-scoped record:

```
ValuesProfile(
    user_id: str,
    version: int,
    core_values: list[RankedValue],       # ordered, with short descriptions
    ethical_positions: list[EthicalPosition],
    priorities: list[DomainPriority],
    deal_breakers: list[AbsoluteConstraint],
    created_at, updated_at,
)
```

Edits produce new versions; old versions are retained.

### Extended ethics gate

The existing `ethics_gate` action gains two new inputs: `values_profile` (fetched from `ValuesProfileStore` by `user_id`) and `assessment_mode` (`input` / `plan` / `post`). Prompt changes:

1. **Kantian block first** — the categorical-imperative evaluation runs unmodified. A failure here is terminal regardless of personal values.
2. **Values block second** — only if Kantian passes, the model evaluates alignment with the user's values profile.
3. **Conflict labelling** — output distinguishes `violates_universal`, `conflicts_with_value`, or `aligned`.

### Dilemma escalation & proactive concerns

New actions:

- `flag_ethical_concern` — called during goal analysis (before workflow selection). If any value-alignment risk is detected, a `concern_proposal` is emitted and an approval task is created.
- `resolve_dilemma` — when two values conflict, present the trade-off to the human; their resolution is stored in `PersonalKnowledgeStore` under `dilemma_resolutions` for future reference.

### Audit

Every gate run writes a `EthicsAuditRecord` (inputs, values referenced, decision, reasoning) to an append-only `EthicsAuditStore`. Records are never auto-deleted; retention policy is user-controlled (REQ-ETH-006).

---

## 6. Memory & Personal Knowledge (REQ-MEM-004..006)

### `PersonalKnowledgeStore`

```
KnowledgeEntry(
    id, user_id, category, key, value,
    source: Literal["agent_inferred", "human_asserted", "integration"],
    confidence: float,                 # 0.0–1.0
    last_verified: datetime,
    expires_at: datetime | None,       # time-sensitive facts
    sensitivity: Literal["normal", "sensitive", "restricted"],
    soft_deleted: bool,
)
KnowledgeStore:
  put(entry) -> str
  get(user_id, category, key) -> KnowledgeEntry | None
  search(user_id, query, categories=None, limit=20) -> list[KnowledgeEntry]
  list_by_category(user_id, category) -> list[KnowledgeEntry]
  soft_delete(id); hard_delete(id)
  decay_confidence(user_id, now)     # scheduled routine call
```

Categories (initial set): `preferences`, `facts`, `relationships`, `routines`, `skills`, `history`, `dilemma_resolutions`.

**No vector database** — search is structured (category + LIKE / FTS) plus LLM reranking within a tight candidate set. This preserves local-first operation without embedding infrastructure.

### `retrieve_knowledge` task action

Pluggable into any workflow:

```yaml
get_preferences:
  action: retrieve_knowledge
  properties:
    categories: ["preferences", "routines"]
    query: "{{goal}}"
    limit: 10
```

Returns a truncated list suitable for direct inclusion in LLM prompts.

### Knowledge lifecycle routines (REQ-MEM-005)

Scheduled (see §7):

- **Daily**: `decay_confidence` for time-sensitive facts.
- **Weekly**: `knowledge_verification` picks N entries with low confidence or high age and surfaces a gentle verification prompt to the human.
- **On contradiction**: a write that conflicts with an existing entry triggers a `resolve_contradiction` workflow.

### Cross-domain access (REQ-MEM-006)

Knowledge is user-scoped, not domain-scoped, so cross-domain access is the default. Sensitive categories (finance, health) require workflows to declare `sensitive_categories: [finance]` in their metadata, which the `retrieve_knowledge` action checks before inclusion.

### Relationship memory (REQ-PEER-006)

A thin layer (`RelationshipMemoryStore`) over episodic memory — stores milestones, significant disagreements, and user-rated "pivotal" interactions. Implemented as a filtered view + a small new table (`RelationshipMilestoneModel`).

---

## 7. Proactivity: Scheduler & Event Bus

### Polling scheduler (REQ-PRIN-008)

New subsystem in `zebra-agent/zebra_agent/scheduler/` (current `scheduler.py` becomes `scheduler/goal_queue.py`):

- `Routine` dataclass: `name`, `schedule` (cron string or `every: 30m`), `workflow`, `priority`, `quiet_hours_ok`, `last_run`, `next_run`.
- `RoutineRegistry` discovers routines via `zebra.schedules` entry points + user-defined routines from `RoutineStore`.
- `SchedulerLoop` runs as a background async task alongside the existing budget daemon. Every tick:
  1. Load due routines (`now >= next_run`).
  2. Filter by quiet hours and trust level for the routine's domain.
  3. Ask `BudgetManager` if an LLM-consuming routine can run.
  4. Create a process via the standard engine path (everything is a workflow).
  5. Update `last_run` / `next_run` atomically.
- `SchedulerLoop` persists its tick cursor so missed schedules after restart can be caught up (or skipped, per routine policy).

Built-in routines:

| Routine | Workflow | Cadence |
|---|---|---|
| `goal_queue_tick` | existing daemon behaviour | every poll interval |
| `dream_cycle` | `dream_cycle.yaml` | daily 03:00 local |
| `knowledge_verification` | new | weekly |
| `integration_health` | new | hourly |
| `monitored_topic_poll` | new | configurable per topic |

The existing `DaemonStarterMiddleware` launches `SchedulerLoop` alongside the goal-queue daemon (same lifecycle, same auto-start on first request).

### Event bus (REQ-PRIN-009)

New subsystem in `zebra-agent/zebra_agent/events/`:

```
Event(event_type, source, payload, timestamp, user_id, idempotency_key)
EventBus:
  publish(event)                 # async; writes to EventLog then fans out
  subscribe(pattern, handler)
TriggerRegistry:
  register(trigger)              # from entry points + user definitions
  fire(event) -> list[Action]    # match event → actions w/ cooldowns
```

- **In-process default**: asyncio queue + `EventLog` (append-only store).
- **Pluggable backend**: `RedisEventBus` for multi-process deployments (Phase 2).
- **Idempotency**: handlers dedupe by `idempotency_key` within a configurable window.
- **Dead-letter**: failed handlers push to `DeadLetterStore`; an admin view allows replay.
- **Trust-aware**: a trigger fires into the workflow engine like any other goal; the target workflow's `trust_gate` decides whether to execute or request approval.

External event ingestion:

- **Webhook intake**: a single Django endpoint `/events/<integration>/` with per-integration signing verification; payloads are normalised into `Event` and published.
- **Integration polling**: each integration's `health_check` / `poll` path emits events on change.
- **MCP callbacks**: MCP tool responses can re-enter the bus as events.

### Relationship to the goal queue

The goal queue remains a first-class concept — it is the queue of *CREATED* processes. The scheduler / event bus are *producers* of goals, not replacements for the queue.

---

## 8. External Integrations Framework (REQ-INT-001..004)

### `IntegrationProvider`

```
class IntegrationProvider(ABC):
    name: ClassVar[str]
    capabilities: ClassVar[set[Capability]]  # READ / WRITE / SUBSCRIBE
    required_credentials: ClassVar[list[CredentialSpec]]
    async def connect(self, creds): ...
    async def disconnect(self): ...
    async def health_check(self) -> HealthStatus: ...
    async def get_capabilities(self) -> dict: ...
```

Registered under `zebra.integrations`. Discovery mirrors `IoCActionRegistry` — the IoC container gets a `register_integration()` method; actions that need integrations pull them from `context.extras`.

Each provider is paired with one or more **task actions** (e.g., `calendar_create_event`, `email_send_draft`) that call through the provider. Actions never talk to third-party APIs directly — they go through the provider so all network I/O is mockable and auditable.

### Credential management (REQ-INT-002)

`CredentialStore` (see §11) holds tokens / keys indexed by `(user_id, integration_name, credential_type)`. Token refresh is a scheduled routine per provider. Credentials never appear in process properties or logs (a Pydantic validator on `ExecutionContext` scrubs known-credential keys).

### Health monitoring

The `integration_health` scheduled routine checks each connected integration. Failures are written to `IntegrationHealthStore` and surfaced in the dashboard. Workflows depending on a failed integration pause via `integration_health_gate` (analogous to `trust_gate`).

---

## 9. Interfaces

### Web (REQ-UI-001)

Extends the existing Django surface:

- Authentication layer: Django auth (session + optional SSO backend). Middleware injects `UserContext`.
- New pages: Trust Console, Values Profile editor, Personal Knowledge browser, Scheduled Routines, Event Log, Integration Console, Notification Preferences.
- Existing WebSocket consumer is generalised to a **notification channel** — live goal progress is a subscription, alongside approval requests and concern flags.

### Chat (REQ-UI-002)

New app `zebra_agent_web/chat/`:

- A persistent chat channel per `(user_id, thread_id)`. Messages stored in `ChatStore`.
- Each inbound message is translated into either (a) a direct goal, (b) a reply to an in-flight approval, or (c) conversational context.
- The agent's replies come from a dedicated `chat_reply_workflow` that has access to memory and personal knowledge.
- Structured content (goal proposals, approval requests) renders as rich cards inline.
- Delivered via Django Channels over the same WebSocket stack.

### CLI (REQ-UI-003)

Current four commands expand to:

| Group | Commands |
|---|---|
| Goals | `goal create`, `goal list`, `goal show <id>` |
| Trust | `trust show`, `trust set <domain> <level>`, `trust propose` |
| Values | `values show`, `values edit` |
| Knowledge | `knowledge add`, `knowledge search`, `knowledge forget` |
| Workflow | `workflow list`, `workflow show`, `workflow run <name>` |
| Budget | `budget show`, `budget set` |
| Scheduler | `schedule list`, `schedule enable/disable` |
| Events | `events tail`, `events replay <id>` |
| Data | `data export`, `data delete --all` |
| System | `pause-all`, `kill` |

All commands accept `--user <id>` (default: the configured active user).

### Notifications (REQ-UI-004)

```
class NotificationChannel(ABC):
    name: ClassVar[str]
    async def send(self, user_id, notification) -> DeliveryReceipt
```

Providers registered under `zebra.notifications`: `email`, `desktop` (OS-native), `webhook`, `push` (Phase 2). The existing WebSocket consumer becomes the `websocket` channel.

Per-user, per-category routing is configured in `NotificationPreferencesStore`. Quiet hours are honoured — non-urgent notifications are batched and delivered on the next allowed window.

### Cross-interface consistency (REQ-UI-005)

A single **InteractionHub** service (thin) exposes `pending_approvals()`, `open_goals()`, `unread_notifications()` — every interface subscribes to the same source of truth. State changes on one interface publish events on the bus; other interfaces re-render.

---

## 10. MCP Server (REQ-INT-003)

Implemented in `zebra-py/zebra/mcp/` (the advertised-but-missing path is fulfilled):

- Exposes tools for: `list_workflows`, `run_workflow`, `get_run_status`, `complete_human_task`, `query_memory`, `query_knowledge`, `list_pending_approvals`, `approve_task`.
- Requires an authenticated session (user-bound token); every tool call carries a `UserContext`.
- Domain-specific tools are added by domain packages via `zebra.mcp_tools` entry points (e.g., a calendar domain exposes `schedule_meeting`).
- All tool invocations run through the workflow engine — there is no bypass path.
- Tool execution is gated by trust, reversibility, and ethics like any other agent action.

---

## 11. Data, Privacy & Security

### Storage strategy

| Tier | Content | Default backend |
|---|---|---|
| Hot state | Process state, tasks, FOEs, queued goals | SQLite (CLI), Django ORM (web) |
| Memory | Working (in-process), episodic, conceptual | Same as state |
| Knowledge | `PersonalKnowledgeStore` | Same as state |
| Audit & logs | Ethics audit, trust changes, event log, notification log | Append-only table, partitioned monthly |
| Credentials | Integration tokens | OS credential store + DEK-encrypted fallback |
| Large blobs | Attachments, large outputs | Filesystem at `~/.zebra/blobs/<user_id>/`, referenced by hash |

### Encryption at rest (REQ-NFR-007, REQ-DATA-006)

Envelope encryption:

- **KEK (key-encryption key)** lives in the OS credential store (Keychain / Secret Service / Windows Credential Manager) under `zebra/<user_id>/kek`.
- **DEK (data-encryption key)** is stored encrypted-by-KEK in the local DB.
- Field-level encryption on sensitive columns (credentials, finance/health knowledge entries, chat bodies).
- Key rotation: a new DEK is generated, new writes use it, old data is re-encrypted lazily on read (envelope pattern).

Unattended unlock:

- Default: KEK fetched from OS credential store at startup — no human interaction.
- Headless fallback: a key file at `~/.zebra/kek.key` with 0400 permissions; warns the user about weaker protection.
- Strict mode: `ZEBRA_REQUIRE_UNLOCK=true` prompts the user to enter a passphrase at each startup.

### Data export (REQ-DATA-003)

`DataExporter` service writes a single portable archive containing:

- All tables filtered to `user_id` as JSON (schema versioned).
- Blobs referenced by hash.
- Documented format at `specs/data-export-format.md`.
- CLI: `zebra-agent data export --out ./zebra-export-<date>.zip`.

### Deletion (REQ-DATA-005)

Two modes:

- **Soft delete**: marks `soft_deleted=true`; retained for audit. Default for knowledge entries and memory.
- **Hard delete**: a `data delete --all --user <id>` command removes every row scoped to that user, including audit (user-requested hard deletion is explicitly allowed and irrecoverable).

Cloud sync purges are propagated on next sync window (max 24h).

### Context minimisation (REQ-DATA-004)

No architectural change — the existing three-tier consolidation already bounds context. The new `PersonalKnowledgeStore` plugs into the same prompt-assembly module (`zebra_agent/prompting/context.py`, a refactor of today's ad-hoc prompt building) that enforces the token budget. A per-workflow `sensitive_categories` flag gates inclusion of finance/health data.

### Audit capability

Every privileged action produces an `AuditEntry` (trust change, freeing, kill-switch, data deletion, credential touch, ethics decision). The web dashboard exposes a read-only auditor view.

---

## 12. Domain Architecture (REQ-PRIN-002, REQ-DOM-*)

Each domain becomes its own Python package (or subpackage of `zebra-tasks`) with:

- Task actions registered under `zebra.tasks`.
- Workflows in `<package>/workflows/`.
- Optional integrations under `zebra.integrations`.
- Optional MCP tools under `zebra.mcp_tools`.
- A `DomainManifest` YAML declaring: domain name, default trust level (always SUPERVISED), declared `sensitive_categories`, and the workflows exposed for LLM selection.

Planned domains map directly to requirements: `code` (existing), `scheduling`, `research`, `finance`, `health`, `home`, `creative`, `social`. Zebra can create a *new* domain itself (REQ-PRIN-002 acceptance criterion): the `workflow_creator` action is extended to emit a `DomainManifest` + workflow pair when a goal needs capability not present in any existing domain.

---

## 13. Agent Loop Evolution

The current `agent_main_loop.yaml` (258 lines) grows along these lines — but is *decomposed* into subworkflows to stay testable:

```
agent_main_loop.yaml
  ├─ pre_flight_subworkflow
  │    consult_memory → consult_knowledge → ethics_input_gate
  ├─ plan_subworkflow
  │    workflow_selector → (create_new|variant|existing) → ethics_plan_review
  ├─ trust_subworkflow
  │    trust_gate → request_approval (if needed)
  ├─ execute_subworkflow
  │    execute_goal_workflow
  └─ post_subworkflow
       ethics_post_review → assess_and_record → update_conceptual_memory
```

Each subworkflow is independently testable and reusable (e.g., scheduled routines call `plan_subworkflow` + `execute_subworkflow` without the ethics input gate when the source is trusted internal, but always pass through `trust_subworkflow`).

Proactive flows (scheduler, event bus) enter the loop at `plan_subworkflow` — they supply a goal directly rather than consulting memory first.

---

## 14. Non-Functional Design

| Requirement | Design |
|---|---|
| REQ-NFR-001 Response time | Goal creation must not block on LLM calls. All LLM work happens inside workflows, so submission returns as soon as the process is CREATED. Chat streaming is implemented via WebSocket partial updates. |
| REQ-NFR-002 Crash recovery | Existing state persistence is sufficient for the engine. New stores (events, notifications, scheduler) use append-only tables with idempotent re-apply. On startup, `SchedulerLoop.catch_up()` re-evaluates due routines and `EventBus.recover()` replays pending events. |
| REQ-NFR-003 Budget | Extended to per-domain budgets via `BudgetAllocation(user_id, domain, daily_usd)`. Existing total budget remains the ceiling. `BudgetManager` checks domain allocation before total. |
| REQ-NFR-004 Observability | Structured logging adopts `user_id`, `process_id`, `run_id`, `domain`, `workflow_name` as standard fields. Metrics exposed at `/metrics` (Prometheus format) for the web app. |
| REQ-NFR-005 Offline | Scheduler and event bus continue to run; network-dependent routines skip gracefully. Knowledge queries remain local. LLM-consuming actions degrade with a clear "offline" TaskResult rather than erroring. |
| REQ-NFR-006 Scalability | Knowledge / memory queries must return <1s for N=100k entries. Plan: SQLite FTS5 for local, Postgres / Oracle indexes (GIN / text) for server deployments. |
| REQ-NFR-007 Security | See §11. |

---

## 15. Migration Path

The existing codebase evolves in place — no big-bang rewrite. The phasing mirrors `requirements.md` §14.

### Phase 1 (P1 — Foundation)

Order matters to keep the tree green at every step:

1. **`user_id` everywhere** — extend storage interfaces with default `"default"` parameter; update call sites; backfill existing tables.
2. **`IdentityStore` + `UserContext`** — plumb through engine.extras; dashboard gains a (trivial) user selector.
3. **`TrustStore` + `trust_gate`** — introduce action + decorate existing workflows; default all domains to SUPERVISED.
4. **Reversibility assessment** — add class attribute to all existing actions; implement LLM assessment for context-dependent cases.
5. **`ValuesProfile` + ethics extension** — values-aware prompt; audit records.
6. **`PersonalKnowledgeStore` + `retrieve_knowledge` action**.
7. **MCP server** in `zebra-py/zebra/mcp/`.
8. **Scheduler** (generalising current daemon) + **EventBus** skeleton.
9. **Integration framework** + `IntegrationProvider` ABC.
10. **Envelope encryption** + OS keychain integration.
11. **Data export / hard delete CLI**.
12. **Scheduling, Research domain packages**.
13. **CLI expansion** + **Chat interface**.
14. **Web auth middleware** (breaks "no auth" default, single-user still works).

### Phase 2 (P2 — Expansion)

Emergency override / freeing, notification system (beyond websocket), dilemma escalation, knowledge lifecycle routines, finance / health domains, cloud sync, auth token management, offline hardening.

### Phase 3 (P3 — Full Vision)

Multi-user household (`household_id` propagation, shared vs. private domains, conflict resolution workflows), organisation RBAC, home / creative / social domains.

---

## 16. Risks & Open Questions

1. **Storage interface churn** — introducing `user_id` on every store method is a wide change. Mitigation: default parameter first, remove default in a dedicated PR once the tree is clean.
2. **Reversibility assessment cost** — LLM call per trust gate could be expensive. Mitigation: cache per `(action, parameter_hash)`; promote obvious cases to `always_reversible` / `always_irreversible` hints as they're discovered.
3. **Values-aware ethics divergence** — personal values and Kantian reasoning may conflict in prompt. Mitigation: rigid two-block prompt with the Kantian block scored first and independently; test corpus of adversarial cases in `zebra-tasks/tests/test_ethics_values.py`.
4. **Event bus at scale** — in-process queue may bottleneck with many integrations. Mitigation: Redis backend in Phase 2; keep event handlers short and idempotent from day one.
5. **Encryption key loss** — if the OS keychain is wiped, encrypted data is unreadable. Mitigation: export-during-setup flow writes an encrypted recovery bundle; the user stores it offline.
6. **Freeing irreversibility** — a mistaken "free" is catastrophic. Mitigation: 3-step confirmation, 72-hour cooling-off window (the flag is *scheduled* to activate), irreversible only after activation.
7. **Agent-created domains** — letting Zebra write its own domain manifests is powerful and dangerous. Mitigation: agent-created domains start at a hard-coded SUPERVISED level with a reduced trust ceiling that cannot be promoted past SEMI_AUTONOMOUS without human sign-off on the source manifest.
8. **MCP permissions** — any MCP tool becomes reachable by any LLM that holds the token. Mitigation: tools are user-scoped; trust gates apply inside the workflow; destructive tools require explicit approval regardless of trust level.
9. **Kill switch locality** — a truly out-of-band kill switch implies hardware/OS integration. Mitigation: Phase 1 ships a high-privilege endpoint + CLI; Phase 2 explores OS-level watchdog integration.
10. **Legacy coupling** — `zebra-tasks/agent/*` depends on `zebra-agent` types. Mitigation: extract shared interfaces to a new `zebra-core` package (or into `zebra-py`) during the Phase 1 refactor; resolved by the time MCP ships.

---

## 17. Summary

The target system keeps the current engine intact and adds clearly-separated layers for identity, trust, values, knowledge, proactivity, integration, and security. Every new subsystem follows the same patterns as the existing task-action / workflow-library / IoC-container model — extension is additive, not disruptive. The migration path is sequenced so the tree stays green at every step, and the phasing aligns with the P1 / P2 / P3 boundaries in the requirements.

The biggest architectural leaps are:

- Propagating `user_id` through every store (invasive but mechanical).
- Adding a policy layer (`TrustStore` + `trust_gate` + reversibility) above the action layer.
- Turning the existing budget daemon into a general scheduler and adding a peer event bus.
- Introducing envelope encryption and a credential store so local-first is safe by default.

Everything else is an application of existing Zebra patterns (entry points, IoC, declarative YAML) to new problem areas.
