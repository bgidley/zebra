## Why

#219 asked for a test that a human task parked on an older workflow version still opens after a
newer version ships. Writing it found the claim was false: on startup, when a built-in workflow
is upgraded, `agent_engine._async_init` deleted **every** stored definition with that name.
Processes pin their definition by id (`sha256(name:version)`), so a process parked on the old
version can then neither render (`/tasks/<id>/` → "Definition not found") nor complete
(`DefinitionNotFoundError`). On prod the #215 deploy deleted *Outcome Review* v3
(`d97ba25d98eed5f4`); no v3 ruling happened to be parked.

The eviction protected nothing: a new version has a new id, so the old row can never shadow it,
and new runs take their definition from the library YAML.

## What Changes

- Startup no longer deletes stored definitions when a built-in workflow is upgraded. The install
  step becomes `agent_engine.install_builtin_workflows(library, builtin_path)`.
- Regression tests park a ruling on the real *Outcome Review* v3, ship v4, and check the ruling
  still renders from v3 (side-by-side table, prior outputs) and completes.

## Non-goals

- Recovering definitions already deleted on prod (old zombie processes; no parked human task is
  affected today).
- The optimizer overwriting a definition with the same name and version (`update_or_create` on the
  same id).

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Upgrading a built-in workflow keeps the old version's stored definition | Test: v4's id differs from the parked process's v3 id; after `install_builtin_workflows` upgrades v3 → v4 (and a second run is a no-op), `load_definition(<v3 id>)` returns v3; the test fails if the old eviction is put back |
| O2 | A human task parked on the old version still renders from its own version | Test: `/tasks/<id>/` for a parked v3 ruling returns 200 with v3's "Verdicts side by side" table and prior outputs, not v4's summary |
| O3 | A parked old-version task can still be completed | Test: completing the parked v3 ruling after v4 ships ends the process COMPLETE |
| O4 | Deploys stop deleting stored definitions on prod | Post-deploy query: no definition id stored before this deploy (30 rows on 2026-10-23) is missing after it, and every row still parses; startup logs no eviction |

(Zebra outcome feedback received: added the id-uniqueness and idempotent re-run checks to O1 and
made O4 checkable right after this deploy. O3 stays because completion goes through the engine's
`_load_definition`, a separate path from the form view.)
