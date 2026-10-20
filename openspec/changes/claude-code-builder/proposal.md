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
  secrets, memory and pids limits, low CPU priority, and a wall-clock limit. An escape probe
  (`zebra_builder.py --probe`) checks the real sandbox. The host never runs git inside the
  workspace the sandbox wrote, and reads its outputs as plain files (no symlinks, size-capped).
- **Capability budget** (#172): every job declares its limits (repo, max turns, minutes).
  The builder rejects a job that asks for more than the server ceilings or names a repo that is
  not allowlisted. It stops a run that exceeds its turns or minutes. Each rejection or overrun is
  logged to the builder audit log and returned to the workflow as `over_budget` or `rejected`.
- **Staging and promotion**: the result stays on the host. Only after a human approves the diff
  (bound to the patch's sha256) does the builder push it, to a new `zebra-build/<job>` branch, and open a **draft** merge
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

Revised after Zebra's feedback (issue #98): O2 is proven by an adversarial probe and names the
token as the one exception; O4 binds approval to the exact patch; O1 and O5 cover the failure,
cancel and restart cases.

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A build goal becomes a reviewed Claude Code change, and a bad build never becomes publishable | Workflow tests: *Build Software* runs brief → confirm → build → review → publish with the builder faked; `failed` / `over_budget` / `rejected` / `cancelled` results fail the workflow without a publish request; a rejected review or cancelled brief never publishes. Builder tests: malformed Claude output, no changes, or a crashed/vanished sandbox give `failed`; failing tests are reported (exit code + log) on the review form, not hidden. On prod, one real small build of gidley/zebra finishes and the review form shows its diffstat, patch, test result, turns and notional cost |
| O2 | The sandbox holds no secret but its own Claude token, and cannot reach the host | `zebra_builder.py --probe` runs the real sandbox command with an escape probe and passes on prod: non-root uid, no effective capabilities, `NoNewPrivs`, only allowed environment names, no host mounts beyond `/workspace` and `/out`, no host paths (`~/.config/zebra`, glab config) visible, no container socket, no writable system dirs. `check_probe` tests show each escape is caught. Builder tests: symlinked or oversized outputs are never read, host git never runs in a sandbox-written workspace, and the token is redacted from all returned text (a patch containing it is refused) |
| O3 | Capability budgets are enforced and every breach is logged | Builder tests: a job over a ceiling or for a repo not on the allowlist is rejected without cloning or starting a container; a run past its minutes is killed and a run that hits max turns is reported, both `over_budget` naming the limit; each case appends an audit-log line, and the watcher records it on the process as `__builder_violations__` |
| O4 | No repository change without human approval of that exact patch | Tests: `publish_build` runs only on the review's `approve` route and sends the reviewed `patch_sha256`; the builder refuses a mismatched (stale) hash, a repo no longer allowlisted, and a second publish; it pushes only `zebra-build/<job>` from a fresh clone with hooks off, then opens a **draft** MR. On prod the approved build appears as a draft MR and master is untouched |
| O5 | A build does not block the goal queue, and survives a deploy | Tests: a build goal parks (external wait, no goal timeout; `find_pending_human_task` hands it off) while not listed as a human task; the watcher delivers each answer once, cancels jobs whose goal ended, and a cancel stops a running sandbox or a queued job; a restarted builder re-attaches to a running sandbox and fails a job whose sandbox is gone. On prod, restarting `zebra-builder` mid-build does not end the build |
