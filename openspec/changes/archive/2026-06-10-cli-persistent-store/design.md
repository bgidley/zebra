## Context

`zebra-agent-web` already has everything F34 needs: `manage.py run_goal` boots Django in
standalone mode and runs a goal against Oracle-backed stores; `cli.py` already has
`_load_env()` and `_setup_django()` helpers and four console entry points; the queue
behaviour exists inline in the `run_goal_queue` web view. F34 packages this as a proper
`zebra` terminal command.

An earlier draft placed the new subcommands in `zebra-agent/cli.py` with an optional
dependency on `zebra-agent-web`. That was rejected: `zebra-agent-web` already hard-depends
on `zebra-agent`, so the optional dep would create a cycle and invert the package layering
(zebra-py → zebra-tasks → zebra-agent → zebra-agent-web).

## Goals / Non-Goals

**Goals:**
- `zebra goal "<text>"` runs a goal, writes metrics/memory to Oracle, prints output.
- `zebra goals` lists recent runs from Oracle.
- CLI-queued goals are indistinguishable from web-queued goals.
- Loud, early failure when the DB backend is not Oracle.

**Non-Goals:**
- Streaming WebSocket output (terminal output via the existing progress callback).
- Changes to the `zebra-agent` package or its CLI.
- Any new Django views or API endpoints.

## Decisions

### 1. Host the CLI in `zebra-agent-web` with a `zebra` entry point

The package that owns the Django stores owns the command that uses them. `cli.py` already
has `_load_env()` + `_setup_django()`; a new `main()` argparse dispatcher reuses them, and
`pyproject.toml` gains `zebra = "zebra_agent_web.cli:main"`. This matches the issue's
literal wording ("`zebra` CLI") and adds zero dependency edges.

Alternative: subcommands in `zebra-agent/cli.py` with optional dep on `zebra-agent-web`.
Rejected — circular dependency, inverted layering (see Context).

### 2. Guard against the silent SQLite fallback

`settings.py` falls back to SQLite when `ORACLE_DSN` is unset — it does not error. Without
a guard, `zebra goal` would "succeed" against a local `db.sqlite3` while the dashboard
reads Oracle, silently breaking the core promise of F34. After `django.setup()`, the
`goal`/`goals` handlers check `connections["default"].vendor`; if it is not `oracle`, they
print which backend is active and how to fix it (`ORACLE_DSN`/`ORACLE_USERNAME`/
`ORACLE_PASSWORD`), then exit 1. An `--allow-sqlite` escape hatch supports local
development against a deliberate SQLite setup.

### 3. Reuse `agent_engine` for goal execution

`zebra_agent_web.api.agent_engine` initialises all stores and the `AgentLoop` with the
Django ORM backends, exactly as `manage.py run_goal` does. The CLI calls
`await agent_engine.ensure_initialized()` then `agent_loop.process_goal(...)` with a
progress callback that prints emitted events. (Note: events come from task actions via
`__progress_callback__` in engine extras; coverage varies by action — the CLI prints
whatever arrives plus a final result block, and does not promise per-task granularity.)

### 4. Extract `queue_goal()` helper; CLI and web view both call it

The queueing logic (resolve model, clamp priority, build properties dict, create CREATED
process) currently lives inline in `web_views.run_goal_queue` (~60 lines). It moves to
`zebra_agent_web/api/goals.py` as `async def queue_goal(goal, *, model=None, priority=3,
deadline=None, user_id=None, identity=None) -> ProcessInstance`. The view keeps its HTTP
parsing and HTML response; the CLI passes parsed args. One code path means CLI-queued and
web-queued goals are guaranteed identical.

Alternative: duplicate the property assembly in the CLI. Rejected — drift risk; this is
exactly the inline logic worth refactoring mercilessly.

## Data Model Changes

None — the CLI writes to the same Oracle tables the web uses.

## API / Interface Changes

New console script in `zebra-agent-web/pyproject.toml`:

```
zebra goal "<text>" [--model haiku|sonnet|opus|kimi] [--queue] [--priority 1-5] [--allow-sqlite]
zebra goals [--limit N] [--allow-sqlite]
```

New module `zebra_agent_web/api/goals.py` with `queue_goal()`; `run_goal_queue` view
refactored to delegate to it (behaviour-preserving).

## Risks / Trade-offs

[Django init overhead] → `django.setup()` + Oracle connect ≈ 0.5–2s per invocation.
Acceptable for a CLI; documented in `--help`.

[View refactor regression] → `run_goal_queue` is exercised by existing e2e tests; the
refactor is behaviour-preserving and covered by them plus a new unit test on `queue_goal()`.

[Per-task progress is best-effort] → The progress callback only receives events actions
choose to emit. The CLI prints what it gets; the final output block is the contract.

## Migration Plan

No schema changes. Merging to master adds the `zebra` script on next install
(`uv sync --all-packages`). Rollback = revert the commit.

## Open Questions

None.
