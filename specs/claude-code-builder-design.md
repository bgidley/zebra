# Claude Code builder: sandboxed builds with capability budgets

Issues: #98 (Zebra changes code through Claude Code), #172 (declared, enforced limits and staging
for what Zebra builds), #251 (delivery stages: Zebra delivers its own changes). OpenSpec:
`openspec/specs/claude-code-builder/spec.md` (changes archived as
`openspec/changes/archive/2026-10-20-claude-code-builder/` and `…-builder-stages/`).

## 1. Goal & scope

Zebra can take a goal like "add X to repo Y", have Claude Code build it in a disposable sandbox,
and deliver it as a **draft merge request**, but only after a human approves the exact patch.

- Claude Code runs headless (`claude -p`) on the owner's **Claude subscription**
  (`CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`), not on OpenRouter.
- **Delivery stages** (#251, §7) let the sandbox run steps of the CLAUDE.md process on Zebra's
  own repo with scoped credentials: `propose`, `ship`, `review`, and `merge` (only for a
  human-approved head). The *Improve Zebra* workflow that drives them is slice B of #251.
- Not in scope: sandbox network egress filtering, parallel builds, a builds page in the UI.

## 2. Architecture

```
zebra-daemon / zebra-web (containers)        host (opc)                       sandbox (podman)
  claude_code_build ──job.json──▶ ~/.local/share/zebra/builds ◀── zebra-builder.service
  await_build (external wait)                  │ clone (host git creds)        Claude Code
  BuilderWatcher ◀──result.json────────────────┤ podman run ─────────────────▶ /workspace, /out
  review_build (human)                         │ read /out (O_NOFOLLOW, capped)
  publish_build ──publish.json──▶              │ fresh clone + git am + push zebra-build/<id>
  await_publish ◀──published.json──────────────┘ glab mr create --draft
```

**Why a host service**: Zebra's containers hold every prod secret, and `python_exec` runs
in-process, so code run there can read them. Mounting the podman socket into Zebra would hand it
the host. The builder is a ~700-line stdlib script that accepts one fixed job schema, which makes
it the capability boundary.

**Sandbox** (`deploy/builder/Containerfile`, Node 22 + Claude Code 2.1.304 + git + uv): runs as
the host uid via `--userns=keep-id`, with `--cap-drop=all`, `no-new-privileges`,
`--memory/--memory-swap` (3g) and `--pids-limit` (512), at `nice 10`. Only the workspace and
output directory are mounted, and the environment holds only the token (passed by name) and the
job parameters. The host delegates only the memory and pids cgroup controllers to rootless podman,
so `--cpus` is opt-in (`ZEBRA_BUILDER_CPUS`). `zebra_builder.py --probe` runs the real command with
`sandbox-probe.sh` in place of Claude Code and checks uid, capabilities, `NoNewPrivs`, environment
names, host mounts, visible host paths, writable system dirs and container sockets
(`check_probe`).

**Hostile workspace**: once a sandbox has run in a workspace, the host never runs git in it again;
`.git/config` and hooks there could execute as `opc`. The builder reads `/out` files with
`O_NOFOLLOW` and only regular files under a size cap, keeps a host copy of the patch, and deletes
the workspace. Publish clones afresh, `git am`s the copy with `core.hooksPath=/dev/null`, and
pushes `HEAD:refs/heads/zebra-build/<id12>`, a ref the builder builds itself. The Claude token is
redacted from every text that leaves the host; a patch that contains it is refused.

## 3. Data model / interfaces

Spool (`ZEBRA_BUILDER_SPOOL`, `/builds` in the containers), one `<job_id>/` (32 hex) per job:
`job.json` (Zebra: kind, repo, base_branch, title, prompt, test_command,
budget{max_turns, minutes}, process_id), `status.json` / `result.json` (builder), `publish.json`
(Zebra: patch_sha256, mr_title, mr_description), `published.json` (builder: branch, mr_url | error),
`cancel` (Zebra). `audit.jsonl` holds one line per rejection, overrun, cancel, failure and publish.

Result: `state` (done | failed | over_budget | rejected | cancelled), `summary`, `diffstat`,
`sensitive_files` (CI / scripts / deploy paths, which the branch pipeline runs on the prod host),
`patch_excerpt` (60k chars), `patch_sha256`, `test {command, rc, log_tail}`, `turns`,
`notional_cost_usd`, `duration_s`, `violations [{limit, requested|used, allowed}]`, `error`.

Zebra side:
- `zebra_tasks/builder/`: `BuilderSpool` (`get_spool(extras)`: `__builder_spool__`, else env),
  `claude_code_build` (`always_reversible`), `publish_build` (`always_irreversible`; needs a `done`
  result and sends its `patch_sha256`).
- `zebra.forms.is_human_task(task_def)`: `auto: false` and no `properties.external`. The web views
  use it, so external waits never show as needing a person. `find_pending_human_task` still sees
  them, so `GoalTracker` parks the goal.
- `zebra_agent/scheduler/builder_watch.py`: `BuilderWatcher.tick()` completes READY
  `external: builder` tasks (`job_key`, `wait_for: result|published`) in background tasks with
  `next_route` = result state (or `published` / `publish_failed`), appends `violations` to
  `__builder_violations__`, and writes `cancel` for live jobs whose process ended. It runs on each
  daemon tick after the kill-switch guard (`make_builder_watcher`; off without a spool).
- Human-form defaults resolve `{{prop.key.subkey}}` at any depth (`_resolve_schema_defaults`).
- Workflow *Build Software* (`zebra-agent/workflows/build_software.yaml`): brief → confirm_brief
  (human, editable budget; `build` / `cancel`) → build → await_build → review_build (human;
  `approve` / `reject`) → publish → await_publish → report (`answer`). A build that is not `done`
  goes to `build_failed` (`propagate_failure`), so the main loop's stuck handoff (#176) can help.

## 4. Control flow

Builder `tick()` (every 5 s, stateless across restarts): for each job, oldest first: `running` →
supervise (`podman inspect`; container gone → `failed`; `cancel` → kill → `cancelled`; past
`minutes` → kill → `over_budget`; exited → collect); `queued`/new → `cancel` → `cancelled`, else
validate (malformed or over a ceiling / not allowlisted → `rejected`, nothing cloned) and start if
no other job is running; `done` + `publish.json` + no `published.json` → publish once. Then prune
finished jobs older than 7 days. `error_max_turns` from Claude → `over_budget`. No result or an
error → `failed`. No patch → `failed`.

A goal parks on `await_build` like a human task: there is no goal timeout, and the daemon picks the
next goal. A deploy restarts the builder, which picks running sandboxes back up from the spool.

## 5. Configuration

| Setting | Where | Default |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | GitLab CI variable (protected, masked) → `~/.config/zebra/builder.env` (never `prod.env`) | none: builds fail "no token" |
| `ZEBRA_BUILDER_REPOS` | `~/.config/zebra/builder-site.env` | `gidley/zebra` |
| `ZEBRA_BUILDER_MAX_TURNS` / `_MAX_MINUTES` | builder-site.env | 200 / 90 |
| `ZEBRA_BUILDER_MEMORY` / `_PIDS` / `_CPUS` | builder-site.env | `3g` / 512 / off |
| `ZEBRA_BUILDER_IMAGE` | builder-site.env | `localhost/zebra-builder-sandbox:prod` |
| `ZEBRA_BUILDER_SPOOL` | builder host default `~/.local/share/zebra/builds`; containers `/builds` (Quadlet) | |
| `ZEBRA_BUILDER_GITLAB_TOKEN` | CI variable (protected, masked) → builder.env | none: `propose`/`ship`/`review` fail. `zebra.gidley`, Developer on `gidley/zebra` (cannot push master) |
| `ZEBRA_BUILDER_GITLAB_MERGE_TOKEN` | CI variable → builder.env | none: `merge` fails. Owner's token, Maintainer+ |
| `ZEBRA_BUILDER_GITHUB_TOKEN` | CI variable → builder.env | none: `ship`/`merge` fail. Fine-grained, `bgidley/zebra`; **expires 2026-11-26** |
| `ZEBRA_BUILDER_SELF_REPO` / `_GITHUB_REPO` | builder-site.env | `gidley/zebra` / `bgidley/zebra` |

Deploy (`scripts/deploy-podman.sh`) installs `zebra_builder.py` to `~/.local/share/zebra/builder/`
and `zebra-builder.service` to `~/.config/systemd/user/`, creates the spool before web restarts,
builds the sandbox image (a failure only warns), and restarts the builder (`KillMode=process`).

## 6. Risks / open questions

- **Token exfiltration**: the sandbox has open network access and holds the subscription token.
  The token only makes model requests and is revocable. Egress filtering is a follow-up.
- **Branch CI runs on the prod host**: pushing `zebra-build/*` starts lint/unit/e2e on the shell
  runner as `opc`, which can read host files. The human approval of the exact patch is the gate;
  the review form says so and lists `sensitive_files`.
- **Shared subscription limits**: builds use the owner's 5-hour and weekly limits; one build at a
  time, bounded by turns and minutes.
- **Self-reported tests**: Claude can edit what the sandbox runs; the review and the MR pipeline
  are the real checks.
- **Notional cost**: `total_cost_usd` is recorded, not added to `__total_cost__`, so
  `DAILY_BUDGET_USD` measures OpenRouter spend only.

## 7. Delivery stages (#251)

A job may name a `stage`; without one it is a `patch` build (everything above, unchanged). Stages
run only on `ZEBRA_BUILDER_SELF_REPO` and take `branch` + `issue`; `merge` also takes
`approval {ship_job_id, head_sha}`. Each gets a stage preamble (`STAGE_PREAMBLE` + `STAGE_STEPS`)
that tells Claude Code which CLAUDE.md steps to do in the sandbox (no podman, prod or worktree
steps; Zebra runs feedback, review and outcome review) and to write `/out/report.json`.

| Stage | Sandbox does | Credentials (`STAGE_TOKENS`) | Builder records |
|---|---|---|---|
| `propose` | read the issue, OpenSpec change with Outcomes, validate, push branch, post outcomes | Developer GitLab | `head_sha`, changed / sensitive files, pipeline |
| `ship` | implement, lint, test, push, watch branch CI and fix (≤3), archive, push GitHub, open PR | Developer GitLab, GitHub | same |
| `review` | independent outcome verdicts in `report.json`; no changes | Developer GitLab | `report.verdicts` required |
| `merge` | detached merge of `head_sha`, push both remotes, delete branch, watch master pipeline | **Maintainer** GitLab, GitHub | `merge_sha`, parents include `head_sha`, pipeline |

- Credentials reach the sandbox as `GITLAB_TOKEN` / `GH_TOKEN` (what glab and gh read), by name;
  `sandbox-run.sh` adds git credential helpers that read them at push time and a `github` remote.
- `propose`/`ship` clone the branch if it exists, else the base plus `checkout -b` on the host
  before the sandbox runs. The other stages clone the base. Stages clone all branches.
- Approval check before cloning: the ship job is a `ship` for the same repo, branch and issue,
  its result is `done` with `head_sha`, and `git ls-remote` still shows that head. Else
  `rejected` + audit; if it passes, a `merge_approved` audit line records the ship job, head,
  branch, issue and process.
- Host facts: `git ls-remote` (host credentials), `glab api` compare / commits / pipelines. A
  stage that pushed nothing, a merge that did not move master or did not merge `head_sha`
  (`merge_mismatch`), a review without verdicts, or any builder credential in a pushed diff
  (`secret_pushed`) fails the stage. `report.json` is capped (100 kB) and redacted. Stage jobs
  are never published.
- `--probe --stage <s>` runs the probe with that stage's real credentials; the probe makes
  read-only `glab api user` / `gh api user` calls and `check_probe` requires the logins and
  allows only that stage's variables.
- Image: glab 1.119.0 and gh 2.103.2 (release checksums pinned), openspec 1.13.2.

Risks: the sandbox's open network now holds push credentials (Developer scope, protected master,
redaction and the pushed-secret check limit this; egress filtering is still a follow-up). The
GitHub token is the owner's and could push the mirror's master (GitHub is not the deploy source).
A compromised Zebra could write its own approval: the human gate is in the workflow, as for
publish.
