## Why

There is no terminal client that shares storage with the web app: the `zebra-agent` CLI
uses in-memory stores only, so goals and memory vanish on exit and never appear in the
dashboard. A `zebra` CLI backed by the same Oracle database turns the terminal into a
first-class client of the same agent — goals submitted from the shell show up in the web
dashboard, and agent memory persists across sessions. Closes #34.

## What Changes

- A new `zebra` console entry point is added to **`zebra-agent-web`** (the package that
  owns the Django ORM stores), with two subcommands:
  - `zebra goal "<text>"` — processes a goal against the Oracle-backed stores and prints
    output; `--model` selects haiku/sonnet/opus/kimi; `--queue` defers to the daemon.
  - `zebra goals [--limit N]` — lists recent runs from Oracle, mirroring the dashboard.
- The web view's inline goal-queueing logic is extracted into a shared helper used by
  both the view and the CLI, so CLI-queued and web-queued goals are indistinguishable.
- The `goal`/`goals` commands verify the active Django DB backend is Oracle and abort
  with a clear message if settings have silently fallen back to SQLite (missing
  `ORACLE_*` env vars).
- The existing `zebra-agent` CLI (credential management) is unchanged.

## Non-goals

- Interactive chat interface (that's F35).
- Multi-user support (CLI is single-user, same as today).
- Changes to `zebra-agent` package — no new dependency edges; `zebra-agent-web` already
  depends on `zebra-agent`, and the CLI lives where the stores live.

## Capabilities

### New Capabilities

- `cli-persistent-store`: `zebra goal` and `zebra goals` subcommands in `zebra-agent-web`
  backed by Oracle, including the Oracle-backend guard, shared queue helper, live
  progress output, and model selection.

### Modified Capabilities

_(none)_

## Impact

- `zebra-agent-web/zebra_agent_web/cli.py` — new `main()` dispatcher + `goal`/`goals` handlers
- `zebra-agent-web/pyproject.toml` — new `zebra` console script
- `zebra-agent-web/zebra_agent_web/api/goals.py` (new) — `queue_goal()` helper extracted
  from `web_views.run_goal_queue`
- `zebra-agent-web/zebra_agent_web/api/web_views.py` — `run_goal_queue` refactored to call the helper
- New tests: unit tests for CLI handlers + one Oracle-backed integration test proving a
  CLI-submitted goal is visible via the same store the dashboard reads
