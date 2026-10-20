## Context

Prod is one 10 GB OCI host running `zebra-web` and `zebra-daemon` under rootless podman. Both
containers hold the Oracle, OpenRouter, Kagi, SMTP and GitLab-issues secrets. `python_exec` runs
in-process, so anything run inside those containers can read every secret. The host user `opc`
can push to GitLab through glab's credential helper, so the host is no safer a place to run
untrusted code either. A goal's auto tasks are failed after 900 s, but time parked on an
`auto: false` task does not count (#142).

## Goals / Non-Goals

Goals: Claude Code builds in a sandbox with no secrets other than its own token; declared and
enforced limits; human approval before anything leaves the host; builds that outlive the goal
timeout and deploys. Non-goals: see the proposal.

## Decisions

### 1. A host builder outside Zebra's containers, talking through a spool directory

Zebra cannot start containers itself; mounting the podman socket would give it control of every
container and, through volume mounts, of `opc`'s home. Instead a small stdlib-only Python service
(`scripts/zebra_builder.py`, run by `uv run --no-project --python 3.12`) runs as `opc` and reads
a fixed job schema from `~/.local/share/zebra/builds`. That directory is mounted into both
containers at `/builds` (`ZEBRA_BUILDER_SPOOL`). The schema is the capability boundary: Zebra can
ask for a build of an allowlisted repo, within the ceilings, and nothing else.

Spool layout, one directory per job, every file written to a temp name and renamed:

```
builds/<job_id>/job.json        Zebra: {kind: build, repo, base_branch, title, prompt,
                                 test_command, budget: {max_turns, minutes}, process_id}
builds/<job_id>/status.json     builder: {state: queued|running|done|failed|over_budget|rejected}
builds/<job_id>/result.json     builder: final result (state, diffstat, patch excerpt, test_rc,
                                 turns, notional_cost_usd, violations, summary)
builds/<job_id>/publish.json    Zebra, after approval: {mr_title, mr_description}
builds/<job_id>/published.json  builder: {branch, mr_url} or {error}
builds/<job_id>/cancel          Zebra: goal ended; builder kills the sandbox
builds/audit.jsonl              builder: one line per rejection, overrun or publish
```

Job ids are `uuid4().hex`. The builder ignores directories whose names are not 32 hex characters.

### 2. The sandbox

`deploy/builder/Containerfile` is based on `node:22-bookworm-slim`, with git, python3, uv and
a pinned `@anthropic-ai/claude-code`. `sandbox-run.sh` runs Claude, commits whatever it left
uncommitted, writes `changes.patch` (`git format-patch <base>..HEAD --stdout`) and `diffstat.txt`,
then runs the job's `test_command` into `test.log` / `test.rc`. Run with:

```
podman run -d --name zebra-build-<id> --userns=keep-id --user <uid>:<gid>
  --memory=<mem> --memory-swap=<mem> --cpus=<cpus> --pids-limit=512
  --security-opt=no-new-privileges --cap-drop=all
  -v <ws>:/workspace:Z -v <jobdir>/sandbox:/out:Z
  -e CLAUDE_CODE_OAUTH_TOKEN -e HOME=/tmp/home -e MAX_TURNS -e BASE_SHA -e TEST_COMMAND
  localhost/zebra-builder-sandbox:prod
```

`--userns=keep-id` makes files the sandbox writes belong to `opc`, so the host can clean them up.
The token is passed by name from the builder's own environment, so it never appears in argv.

The workspace is a clone the host made. After the sandbox has run, the host treats it as hostile:
`.git/config` or hooks there could run commands as `opc`. The host never runs git in it again.
It reads only `/out` files, with `O_NOFOLLOW`, requiring a regular file and capping the size.
Publish clones the repo afresh, `git am`s the patch into it with hooks disabled, and pushes from
there.

### 3. Capability budget (#172)

Ceilings come from `builder.env`: `ZEBRA_BUILDER_REPOS` (allowlist, default `gidley/zebra`),
`ZEBRA_BUILDER_MAX_TURNS` (200), `ZEBRA_BUILDER_MAX_MINUTES` (90), `ZEBRA_BUILDER_MEMORY` (3g),
`ZEBRA_BUILDER_CPUS` (1.5). A job outside them is `rejected` before any clone. Minutes are
enforced by the builder, which kills the container when they run out. Turns are enforced by
`claude --max-turns`; a result of subtype `error_max_turns` is reported as `over_budget`. Every
breach is a `violations` entry `{limit, requested|used, allowed}`, appended to `audit.jsonl`;
`claude_code_build` copies it into `__builder_violations__` on the process.

### 4. Parking while the builder works

`claude_code_build` writes the job and returns `{job_id}`. The next task is an external wait:

```yaml
await_build:
  auto: false
  properties: {external: builder, job: "{{build_job.job_id}}"}
```

The process parks: no goal timeout runs, and the daemon's `GoalTracker` hands the goal off as it
does for a human task. `BuilderWatcher.tick()` runs at the start of every daemon tick. It finds
READY tasks with `external: builder`, reads the job's `result.json` (or `published.json`), and
calls `engine.complete_task(task_id, TaskResult.ok(output=result, next_route=state))`. For every
job whose process is FAILED or COMPLETE while the job is still live, it writes `cancel`.
`zebra.forms.is_human_task(task_def)` (`not auto and not properties.external`) replaces the bare
`not task_def.auto` check in the web views, so external waits are never shown as needing a human.
`find_pending_human_task` still returns them, so the tracker parks the goal.

### 5. Restart safety

The builder keeps no state outside the spool. On start, for each job in `running` it checks
`podman container exists zebra-build-<id>`: if the container exists it resumes supervising it,
otherwise it marks the job `failed` ("builder restarted and the sandbox is gone"). Deploys
restart the builder but never stop sandboxes.

### 6. Publish

`publish_build` runs only on the review's `approve` route. It writes `publish.json` and the
workflow parks on a second external wait. The builder:
1. rechecks the repo against the allowlist;
2. makes a fresh clone, runs `git am` with `-c core.hooksPath=/dev/null`, and pushes
   `HEAD:refs/heads/zebra-build/<job_id[:12]>`. The ref is built by the builder; nothing from
   the job can change it;
3. runs `glab mr create --draft --source-branch … --target-branch <base>`;
4. writes `published.json` and deletes the workspace.

A rejected review writes `cancel`, which deletes the workspace. Workspaces older than 7 days are
pruned.

### 7. Cost

Claude Code reports `total_cost_usd` even on a subscription; we record it as `notional_cost_usd`
and never add it to `__total_cost__`, so `DAILY_BUDGET_USD` keeps measuring real OpenRouter
spend. The brief and summary `llm_call`s are normal OpenRouter calls.

## Risks / Trade-offs

- **Token exfiltration**: the sandbox has unfiltered network access and holds the subscription
  token. A prompt-injected Claude could send it out. Mitigation: the token can only make model
  requests and can be revoked. Egress filtering through a proxy is a follow-up.
- **Subscription limits**: builds share the owner's 5-hour and weekly limits. One build runs at
  a time, with `max_turns` and minutes as the brake.
- **Host memory**: a 3 GB sandbox, plus web (1.5 GB) and daemon (768 MB), fits in 10 GB with the
  runner, but not two builds; hence one at a time.
- **Self-reported tests**: Claude can edit the tests the sandbox runs. The human review and the
  MR's GitLab pipeline are the real checks.
