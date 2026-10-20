## Why

Zebra cannot build software. It can write files with an LLM and run Python snippets in its own
process, but it has no workspace, no test run, no commits and no long coding loop, so an
ambitious build goal produces unchecked text. #98 asks for Zebra to change code through Claude
Code; #172 (Zebra's own request) asks that anything Zebra builds runs inside declared limits and
stays staged until it passes review. This change does both at once. Closes #98, closes #172.

## What Changes

- **Host builder** (`scripts/zebra_builder.py`, `zebra-builder.service`): a small host service
  that takes build jobs from a spool directory shared with Zebra's containers. For each job it
  clones the repo, runs headless Claude Code (`claude -p`) in a throwaway podman sandbox, then
  writes back the patch, diffstat, test result, turns and notional cost. Claude Code bills to the
  owner's Claude subscription (`CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`), never to
  OpenRouter.
- **Sandbox** (`deploy/builder/`): a Node + Claude Code + git + uv image. Each container runs as
  a non-root user with only the workspace and job directory mounted, the Claude token and no other
  secrets, and memory, CPU, pids and wall-clock limits. The host never runs git inside the
  workspace the sandbox wrote, and reads its outputs as plain files (no symlinks, size-capped).
- **Capability budget** (#172): every job declares its limits (repo, max turns, minutes).
  The builder rejects a job that asks for more than the server ceilings or names a repo that is
  not allowlisted. It stops a run that exceeds its turns or minutes. Each rejection or overrun is
  logged to the builder audit log and returned to the workflow as `over_budget` or `rejected`.
- **Staging and promotion**: the result stays on the host. Only after a human approves the diff
  does the builder push it, to a new `zebra-build/<job>` branch, and open a **draft** merge
  request. It never pushes to master or merges anything.
- **Zebra side**: task actions `claude_code_build` and `publish_build` write jobs. The workflow
  parks on an external-wait task (`auto: false`, `external: builder`) while the builder works, so
  the 900 s goal timeout and the goal queue are unaffected. A `BuilderWatcher` in the daemon tick
  completes that task when the result lands, and cancels the job when its goal ends early.
  External-wait tasks are not shown as human tasks.
- **Workflow** *Build Software*: brief (llm_call) → human confirms brief and budget → build →
  summary → human reviews the diff → publish draft MR, or discard.
- Deploy writes `builder.env` (token, ceilings) from CI variables, builds the sandbox image,
  mounts the spool into `zebra-web` / `zebra-daemon` and installs and restarts the builder unit.
  Restarting the builder re-attaches to running sandboxes, so deploys do not kill builds.

## Non-goals

- Merging to master or deploying: promotion stops at a draft MR; humans merge.
- Network egress filtering inside the sandbox (Claude needs the API, git and package indexes).
  Recorded as a risk.
- Running builds in parallel: one at a time (single 10 GB host).
- Counting subscription usage against `DAILY_BUDGET_USD`: Claude Code's reported cost is notional
  and recorded separately.
- A dedicated builds page in the UI; the run trace and the review form show the build.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A build goal becomes a reviewed Claude Code change | Workflow tests: *Build Software* runs brief → confirm → build → review → publish with the builder faked, routing `done` / `failed` / `over_budget` / `rejected` correctly; on prod, one real small build of gidley/zebra finishes and the review form shows its diffstat, patch, test result, turns and notional cost |
| O2 | The sandbox gets no secrets and cannot reach the host | Builder unit tests: the `podman run` command has non-root keep-id user, memory, CPU and pids limits, only the workspace and job mounts, and only the Claude token in its environment; output reads refuse symlinks and oversized files; host git never runs in the sandbox-written workspace (publish applies the patch to a fresh clone). On prod, `podman inspect` of a build container shows the same |
| O3 | Capability budgets are enforced and every breach is logged | Builder tests: a job over a ceiling or for a repo not on the allowlist is rejected without starting a container; a run past its minutes is killed and a run that hits max turns is reported, both as `over_budget` naming the limit; each case appends an audit-log line and reaches the process as `__builder_violations__` |
| O4 | Nothing leaves the sandbox without human approval | Tests: `publish_build` runs only on the review's `approve` route; the builder pushes only `zebra-build/<job>` branches on allowlisted repos and refuses any other ref; on prod the approved build appears as a draft MR, and master is untouched |
| O5 | Builds never block Zebra or die with a deploy | Tests: a build goal parks (no goal timeout while it runs, the queue picks the next goal); `BuilderWatcher` completes the wait task when the result lands and writes a cancel when the goal has failed; a restarted builder re-attaches to a running sandbox by name. On prod, a deploy during a build does not end it |
