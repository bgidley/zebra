## Why

The Dream Cycle rewrote prod's *Compute* to a broken v3 (unregistered condition, name-only `subworkflow`), so the post-deploy smoke test `test_smoke_count_to_100` is red (#327). The owner-approved route is the #224 mechanism: ship the built-in above the dream copy's version.

## What Changes

- Built-in `compute.yaml` version 1 -> 4 (above the prod dream v3 and the v2 `compute_1.yaml` copy). Content unchanged. At startup `copy_builtin_workflows` reinstates it and retires the dream copies.
- Tests: a higher built-in replaces a lower-versioned dream rewrite of the same file (prod layout); the shipped Compute version stays above 3.

## Non-goals

- Editing prod data. The Dream Cycle validation gap and the 404 on a parked goal's status are follow-up issues.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A built-in with a higher version replaces a lower-versioned dream copy of the same name | Unit tests in test_library.py |
| O2 | Shipped Compute is version 4, above the broken v3 | Test plus diff |
| O3 | After deploy, prod's Compute is the built-in again (read-only check) | `podman exec zebra-web` shows version 4, no dream parent |
| O4 | Post-deploy smoke goes green | GitLab pipeline |
