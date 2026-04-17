# Zebra Backlog

Concrete, actionable items not captured as requirements in [docs/requirements.md](../docs/requirements.md). Requirements describe *what* the system must do; this file tracks *what's left to build/fix* to get there.

**Status legend:** ❌ Not started ⚠️ Partial ✅ Done

---

## Task Actions Library

The entry-point pattern (REQ-PRIN-002) is in place; these concrete actions are missing.

- [ ] HTTP/REST client — GET/POST/PUT/DELETE with auth (bearer, basic, API key)
- [ ] Database ops — query/insert/update/delete against SQLite, Postgres, Oracle
- [ ] Git ops — clone, commit, push, pull, branch, diff
- [ ] Email / webhook notifications — SMTP send, generic webhook POST
- [ ] Data transforms — CSV parsing, JSON manipulation, XML parsing
- [ ] Archive ops — zip/tar create and extract
- [ ] Template rendering — Jinja2, Mustache
- [ ] Web search action
- [ ] OpenCode / Claude Agent SDK as a task action (delegating a sub-goal to an external coding agent)

Package layout: `zebra-tasks/zebra_tasks/{http,database,git,notifications,data,archive,template,search,agent_delegate}/`.

---

## Workflow Engine — Control-Flow Patterns

9 of 43 WCP patterns implemented (see [../zebra-py/workflows.md](../zebra-py/workflows.md)). Priority additions:

- [ ] WCP-9 Structured Discriminator — first-wins, ignore rest
- [ ] WCP-16 Deferred Choice — runtime path selection
- [ ] WCP-18 Milestone — state-based activation
- [ ] WCP-22 Recursion — self-referential workflows
- [ ] WCP-28 Blocking Discriminator — M-out-of-N completion
- [ ] WCP-33 Static Partial Join for Multiple Instances
- [ ] WCP-41 Thread Merge — safe concurrent path merging

---

## Learning & Cost

Items the requirements reference only in passing (REQ-NFR-003 budget, REQ-DOM-CODE-001 dream cycle) but that need concrete work.

- [ ] **Parallel-comparison voting** — when the agent is uncertain, run two workflow variants in parallel and present both outputs to the human to pick a winner. Feeds episodic memory.
- [ ] **Cost-aware model routing** — pick Haiku/Sonnet/Opus per task based on complexity and remaining budget. Resolution order already exists (task > process > server default); the missing piece is the *decision policy*.
- [ ] **Self-improvement via Claude Agent SDK** — let Zebra edit its own code/workflows via the SDK, not only YAML edits. Distinct from dream cycle, which operates on metrics and workflow structure.

---

## Operational Concretion

REQ-NFR-004 (observability) and REQ-NFR-007 (security) are stated at principle level. Concrete deliverables:

### Observability

- [ ] Prometheus metrics endpoint (workflow duration, cost, success rate, per domain)
- [ ] OpenTelemetry tracing across engine + task actions
- [ ] Structured JSON logging with correlation IDs
- [ ] Health check endpoints (liveness, readiness)
- [ ] Sentry (or equivalent) error tracking integration
- [ ] Dashboard tiles for memory-system metrics (entries by category, query latency, storage size)

### Security

- [ ] Auth on web dashboard + API (JWT or session-based) — single-user default
- [ ] Rate limiting on public endpoints
- [ ] Input validation + sanitisation at API boundaries
- [ ] TLS termination guidance / reverse-proxy docs
- [ ] Dependency vulnerability scanning in CI
- [ ] Audit log of all external API calls (supports REQ-NFR-007 acceptance criterion)

### Performance

- [ ] SQLite/Postgres indexing review for process + task queries
- [ ] Connection pooling for DB and HTTP task actions
- [ ] Optional Redis cache layer for hot lookups (memory, conceptual index)
- [ ] Lazy-load workflow definitions (don't parse all YAML on startup)
- [ ] Batch task state transitions where the engine processes multiple ready tasks

---

## Test Coverage

- [ ] End-to-end suite covering agent main loop from goal → assess_and_record
- [ ] Performance regression suite (throughput, p95 latency on representative workflows)
- [ ] Chaos tests — fault injection at storage and LLM provider boundaries
- [ ] Load tests — high-volume queued goals, concurrent processes
- [ ] Security tests — injection, auth bypass, credential leakage in logs
- [ ] Browser tests for the web dashboard (Playwright)

---

## User-Facing Documentation

Requirements reference docs but don't enumerate them.

- [ ] Getting Started tutorial — create your first goal end-to-end
- [ ] User Guide — values profile, trust levels, memory, domains
- [ ] Auto-generated API reference from docstrings
- [ ] Migration guide for users of the legacy Java implementation
- [ ] Troubleshooting guide — common errors, log interpretation
- [ ] Deployment guide — single-user local install, optional Docker

---

## Known Bugs / Follow-ups

- [ ] Feedback form — verify learning loop is actually updating episodic/conceptual memory when a human submits a rating.

---

## Out of Scope

Dropped from the old `TODO.md` because they conflict with local-first / single-user posture (REQ-PRIN-005, REQ-USR-001) or are speculative:

- Multi-node distributed execution, gRPC coordination, etcd/Redis consensus
- Multi-agent collaboration protocols between Zebra instances (superseded by REQ-PRIN-007 workflow sharing, which is lighter-weight)
- Knowledge graph integration (Neo4j / Neptune)
- Natural-language-to-YAML workflow generation
- Meta-learning, genetic algorithms, reinforcement learning, counterfactual reasoning
- Kubernetes / Helm / Terraform / blue-green deployment tooling
