# Multi-Device and Multi-User Data Model (server + Oracle)

**Status**: Draft (revised 2026-10-25; supersedes the 2026-04-16 local-first CRDT draft)
**Issues**: #57, #58 (closed), #59, #60, #61 (deferred), #242, #243 (`phase::18-multi-user`)
**Relates to**: REQ-USR-001..005, REQ-DATA-001/002, REQ-PRIN-005, REQ-NFR-005, REQ-NFR-007
**Decision (owner, 2026-10)**: Zebra stays a server backed by Oracle. SQLite is not a target.
A local database may come later, so use only features common to Oracle and PostgreSQL.

---

## 1. Goal & scope

Zebra is a server: one deployment (today a single OCI host running `zebra-web` and one
`zebra-daemon` under rootless Podman, see [podman-single-host-design.md](podman-single-host-design.md))
backed by one Oracle ADB schema through the Django ORM stores. This doc says what
"multi-device" and "multi-user" mean on that model.

- **One Zebra = one deployment = one Oracle schema = one household.** No teams for now.
  The server is the only source of truth. There is no per-device database and nothing to merge.
- **Multi-device** (#57): a device is a *client* (browser, phone, tablet, CLI, API caller) of that
  one Zebra. Each device has its own passkey or API token, which can be listed and revoked.
- **Multi-user** (#59): several Django users on the same schema. Each record has an owner
  and a scope (`private` or a shared domain). Scoping is enforced in the store layer and fails closed.
- **Conflict mediation** (#60) is a workflow problem: Zebra notices that two people want
  incompatible things and runs a mediation workflow with human tasks for each party. Concurrent
  edits to one row are handled by optimistic concurrency, not CRDTs.

**Out of scope / deferred**

- True local-first or offline operation, and any per-device replica (cr-sqlite, CRDTs).
  An offline read-only cache is a client concern and may come later as a PWA.
- Replicating *data* between two Zebra deployments (e.g. a home Zebra and a work Zebra).
  *Workflows* move between deployments only through Commons S3b (#236). Data stays put.
- Several households in one deployment (multi-tenancy). Another household runs its own Zebra.
- Client-side end-to-end encryption. The server must read data to act on it.
- Multi-host or HA Zebra. There is one daemon per deployment (kill switch in `SystemStateModel`).
- Team / organisation support (#61, REQ-USR-004): deferred by the owner.
- Database-specific row security (Oracle VPD) and any other Oracle-only feature in core paths.

### What the April 2026 draft said that is now superseded

| April draft | Now |
|---|---|
| Local SQLite on every device, cr-sqlite CRDT tables, vector clocks, merge semantics per type (§4) | Dropped. Oracle is the single store, and writes are serialised by the DB. |
| Signed capability tokens, keypair trust chain and revocation lists for *data access* (§5) | Dropped. Access control is server-side: Django users, roles and domain membership. Keys stay only where Commons needs them (#228). |
| LAN mDNS peer sync, WebSocket peer protocol, encrypted relay for data changesets (§6) | Dropped. Devices talk HTTPS to the one server. No data relay (#58 closes, see §7). |
| Phase 2 cloud sync = Phase 3 multi-user transport (§8) | Phase 2 "cross-device" is already met by the web UI. Multi-user is a schema/scoping change. |
| "Centralised DB + server RBAC" rejected (§3.1) | Adopted. It matches how Zebra is deployed. |

Two ideas carry over: private data is *invisible* to other users, not just read-protected, and the
data classes split into private and shared.

---

## 2. What exists today (baseline)

- **Identity**: Django users with passkeys (F4/F5). Single-user identity (display name, identity
  UUID) lives on the singleton `SystemStateModel`. Cloudflare Access admits only the owner.
- **Namespacing (F6)**: `user_id` on processes, tasks, runs, task executions, workflow/conceptual
  memory and postmortems. Knowledge, values profile, trust, ethics audit are already keyed per user.
  `CurrentUserMiddleware` puts the request user in a `ContextVar`. Django stores filter by it
  **only when it is set**, so code with no request (daemon, routines, management commands) sees
  every user's rows (*fail-open*).
- **Goal submitter (#151)**: every goal entry point stamps `__user_id__` and identity keys on the
  process, and child workflows copy them. Routine goals run as the owner (`resolve_routine_user`).
- **Not per user**: the LLM spend ledger (`zebra_llm_spend`), the workflow library (a shared volume),
  the kill switch and the daily budget.
- **Credentials (F7)**: `CredentialStore` keyed by `(user_id, integration, type)`. In the
  container it falls back to `FileCredentialStore`. Deploy-time secrets come from `prod.env`.
- **Loose end**: any signed-in user can register a passkey under a *new* username, which creates
  a new Django user. There is no invite or role model.

---

## 3. Data model

### 3.1 Members and roles

`HouseholdMember` (one row per Django user; replaces the identity fields on `SystemStateModel`):
`user_id` (PK, FK `auth_user`), `display_name`, `identity_id` (UUID), `role`
(`owner` | `member` | `guest`), `joined_at`, `active`.

- The first user is `owner`. Only an owner can invite members, change roles or deactivate members.
- `guest` sees only domains it is explicitly given and cannot raise trust levels.
- No extra guardrails for children or guests beyond the `guest` role for now.

### 3.2 Domains and scope

The shared/private unit is the **trust domain** (the existing eight-domain registry in
`zebra_agent/storage/trust.py`, e.g. `finance`, `home`, `health`). Scoping reuses that list.

`DomainShareModel`: `domain`, `user_id`, `access` (`read` | `write`). A domain with no rows is
private to each user. A user who is a member of a shared domain sees all rows scoped to it.

Every user-data row gets two columns:

| Column | Meaning |
|---|---|
| `user_id` | Owner (author/submitter). Already present on most tables. `NULL` only for system rows. |
| `scope` | `private` (default) or `shared:<domain>`. |

Visibility rule, the only one: a viewer sees a row iff `row.user_id == viewer` **or**
(`row.scope == shared:D` and viewer has a `DomainShareModel` grant on `D`). System rows
(`user_id IS NULL`, e.g. built-in workflow memories) are visible to all members.

### 3.3 Scoping by data class

| Data | Owner | Default scope | Notes |
|---|---|---|---|
| Goals, processes, tasks, runs, task executions | submitter | `private`; `shared:D` when the goal is filed in a shared domain | Children inherit the root's owner and scope. |
| Episodic / conceptual memory, postmortems | goal owner | follows the run | `clear_conceptual_memories` must scope by user (F6 latent bug). |
| Personal knowledge | user | `private` | A user may move an entry into a shared domain. Agent-learned entries (F152) start private. |
| Values profile, values tags | user | **always private** | Never shareable. Each person's ethics context is their own (REQ-USR-003). |
| Trust levels, suggestions, freeing | user | per (user, domain) | Shared-domain actions use the **most restrictive** level among the domain's write members (decided). |
| Ethics audit | goal owner | follows the run | |
| Credentials | user, or household (`user_id NULL`) | per user | A household credential (e.g. the shared calendar) is owner-managed and usable only by goals in its domain. Stored in a new `DjangoCredentialStore` table (decided); at rest it relies on Oracle TDE. |
| Workflow library | the Zebra | shared by all | Skills belong to the Zebra, not a person. The leak guard (#237) keeps run content out of them. |
| LLM spend ledger | goal owner | — | Add `user_id`, taken from the root process's `__user_id__`. |
| Kill switch, budget settings, routines | the Zebra | — | Owner-managed. Any member can halt; only the owner resumes (assumed, Q1). |

### 3.4 Migration

- Add `scope` (default `private`) to the tables above, `user_id` to `zebra_llm_spend` and the
  remaining stores. Backfill existing `NULL` `user_id` to the owner (as migration 0011 did).
- Move `SystemStateModel.user_display_name/user_identity_id` into a `HouseholdMember` row for the
  owner, and keep reading the old fields for one release.
- Plain columns and composite indexes `(user_id, scope)`, portable to PostgreSQL. No VPD (decided).

---

## 4. API / interface changes

- **Store layer**: one helper, `visible_to(qs, viewer)`, in `zebra-agent-web`, applied by every
  Django store read. Abstract store ABCs take an explicit `viewer: int | None` where they don't
  already take `user_id` (closes the "Partial" REQ-USR-002 gap in the as-is).
- **Fail closed**: a read with no viewer and no explicit `system=True` raises. Daemon code, routines
  and task actions pass the process's `__user_id__` as the viewer. The ContextVar stays as the
  request default.
- **Members**: `/settings/members/` (owner): invite (one-time link, the invitee registers a passkey),
  role, deactivate. `begin_register` only accepts a new username with a valid invite.
  Cloudflare Access must also admit the member's email (deploy config, not code).
- **Devices** (#57): `/settings/devices/` lists the user's passkeys and API tokens (label, created,
  last used) with rename and revoke. Per-device API tokens serve the CLI and other API clients.
- **Goals**: the goal form and `POST /api/goals/` take an optional `domain`. A domain the user
  shares sets `scope = shared:<domain>`.
- **Assigned human tasks**: a task definition may set `properties.assignee` (a user id, a template
  such as `{{__user_id__}}`, or `members:<domain>`). Human-task lists show a user only the tasks
  assigned to them, plus unassigned tasks on processes they can see. This is the primitive #60 needs.
- **Optimistic concurrency** on shared editable rows (knowledge, shared settings): a `version`
  column, and an update with a stale version returns `409` with the current row. No merging.

---

## 5. Control flow

### 5.1 One daemon, many humans

The single daemon and the single **daily budget** (the Zebra's wallet) stay. Additions:

- **Attribution**: each ledger row carries the goal owner, so the dashboard shows spend per member.
- **Fair share**: `GoalScheduler.score_process` subtracts a term for the submitter's spend today
  and goals already started today, so one member's queue can't starve another's. Priority and age
  still apply. With one user this is a no-op.
- **Optional per-member cap**: `MEMBER_DAILY_BUDGET_USD` (default unset = only the global cap).
  A goal over its owner's cap waits in the queue with a reason, as the global cap does now.
- Goals parked on human tasks are handed off as now (#141), so a slow member doesn't block the queue.

### 5.2 Conflict mediation (#60)

Mediation is a workflow, `household_mediation.yaml`, not a storage feature:

1. **Detect**: when a goal is filed in a shared domain, a low-tier `detect_conflict` step compares
   it with other members' active goals and shared-domain knowledge in that domain. It routes
   `no_conflict` (carry on) or `conflict`.
2. **Hold**: the contested goal waits (REQ-USR-005 "patient for consensus"). Nothing irreversible
   runs on a contested decision.
3. **Propose**: Zebra writes a compromise with its reasoning and the trade-offs, using each
   party's values profile only to reason privately. It shows each party only what that party may see.
4. **Consult**: one human task per party (`assignee` = that member). Each can agree, object
   with a reason or counter-propose. The task loops until all agree or a deadlock rule fires.
5. **Deadlock**: an ethics gate proposes a safe default (energy saving, least waste, safer option)
   that harms no party. It is still shown to all parties before it applies.
6. **Record**: the outcome goes to episodic memory scoped `shared:<domain>`, and later
   detections use it.

No member outranks another, including the owner. Owner powers are admin powers, not a casting vote.

---

## 6. Configuration

| Setting | Env var | Default | Purpose |
|---|---|---|---|
| `MEMBER_DAILY_BUDGET_USD` | `ZEBRA_MEMBER_DAILY_BUDGET_USD` | unset | Optional per-member daily cap under the global budget |
| `FAIR_SHARE_WEIGHT` | `ZEBRA_FAIR_SHARE_WEIGHT` | 1.0 | Weight of the submitter's spend/starts in goal scoring; 0 disables |
| `MEMBER_INVITE_TTL_HOURS` | `ZEBRA_MEMBER_INVITE_TTL_HOURS` | 48 | Lifetime of a member invite link |

Also the Cloudflare Access policy must list every member. That is deploy config, outside the repo.

---

## 7. What happens to the old issues

- **#57** becomes device and session management for the one server (§4 Devices). Offline is deferred.
- **#58** closes: there is no data to relay. Moving workflows between deployments is Commons S3b
  (#236), whose private relay carries only workflows. Data replication between deployments is deferred.
- **#59** becomes members, roles, domain shares and fail-closed scoping (§3, §4).
- **#60** becomes the mediation workflow plus assigned human tasks (§4, §5.2).
- **#61** is deferred: no teams for now (REQ-USR-004 deferred).
- **#242 (B0)**: fail-closed per-user scoping in every store, before #59.
- **#243 (B4)**: fair share and per-member spend under one budget, after #59.

Commons (#41) is unaffected. Its Zebra key belongs to the deployment, so in a household it is the
household's Zebra that holds reputation. A Commons "device" (home, work) is a separate Zebra
*deployment*, not a phone or browser.

---

## 8. Decisions (owner, 2026-10-25)

| Question | Decision |
|---|---|
| Requirements written for local-first | Reworded: data lives in the deployment's own database (cloud Oracle now, maybe local later). REQ-PRIN-005, REQ-DATA-001/002 rewritten; REQ-NFR-005 offline deferred. |
| Encryption at rest | Oracle TDE is enough. No application-level column encryption. |
| Oracle VPD as second line of defence | No. App-level scoping only, and avoid Oracle features PostgreSQL lacks. |
| Shared-domain trust | Most restrictive level among the domain's write members. |
| Per-member credentials backend | A database table (`DjangoCredentialStore`). |
| Team / organisation (#61) | No teams for now. |
| Children / guest guardrails | Nothing beyond the `guest` role for now. |
| Commons "device" | Home and work are separate deployments, not clients. |

### Open questions / risks

1. **Kill switch and freeing** (not yet decided; assumed): any member can halt, only the owner
   resumes, and freeing (F17) is per member and not allowed in shared domains.
2. **Known Oracle-only feature**: in-database embeddings (`zebra-agent-web/zebra_agent_web/embeddings.py`)
   must stay behind the memory store interface, with pgvector plus an external embedding model as
   the PostgreSQL path.
3. **Scoping bugs** are the main risk once a second person joins. #242 makes every read fail closed
   and adds a two-user leak test over every endpoint.
