---
name: "CI/CD: Commit → Monitor → Fix → Merge"
description: Ship the current feature branch via the cicd-manager agent, then run the outcome review and clean up.
category: Workflow
tags: [cicd, gitlab, merge, automation]
---

Ship the current feature branch end to end. Delivery itself (lint, test, commit, push, watch
CI, fix, archive OpenSpec, PR, merge, verify master + prod) is done by the **`cicd-manager`**
agent, so there is one definition of it: `.claude/agents/cicd-manager.md`. This command only
prepares the hand-off and does the steps that agent can't: the outcome review and cleanup.
`CLAUDE.md` (**Version Control & CI/CD**) is the source of truth for all of it.

**Input**: Optional commit message override.

---

## Step 1 — Orient

Run `git branch --show-current` and `git status`.

- On `master`: stop and tell the user to work on a feature branch.
- Derive the issue `#N` from `fN/description`, and the feature title from the OpenSpec
  proposal (`openspec/changes/*/proposal.md`) or the issue (`glab issue view N --repo gidley/zebra`).
- Note whether you're in a worktree (`.claude/worktrees/` in the path) and the worktree path.

## Step 2 — Delegate delivery

Launch the `cicd-manager` agent with: the branch, issue `N`, the title, any commit message
override, and the exact `Co-Authored-By` trailer this session uses. Wait for its report.

- **FAILURE**: relay the failing stage, log excerpt and git state to the user, and stop.
  Don't retry blindly; fix the cause or ask.
- **SUCCESS**: note the master base, merge sha and prod `short_hash`, and continue.

## Step 3 — Outcome review (#190)

Skip for trivial changes (docs-only, one-line fixes). Otherwise, as CLAUDE.md describes: a
fresh Claude subagent with no context reviews `git diff <master base>..<merge sha>` against
the proposal's `## Outcomes` and writes `claude.json`, then:

```bash
bash scripts/zebra-outcome-review.sh run <N> "<title>" outcomes.md claude.json <master base> <merge sha>
```

- Exit 0: post the table on the issue and file follow-up issues (`Refs #N`) for any it lists.
- Exit 2: a human must rule. Tell the user and poll `status <process_id>` until it exits 0.
- Exit 1: fix the review or report it. Never sign off without one.

## Step 4 — Clean up

Follow CLAUDE.md **After the master pipeline is green, clean up**:

1. In a worktree: check `git status --porcelain` is empty and
   `git merge-base --is-ancestor HEAD origin/master` succeeds, then `ExitWorktree` with
   `action: "remove"`.
2. Fast-forward the main checkout only if it is on `master` with no local changes.
3. Delete the local branch once it is in `origin/master`.

## Step 5 — Final report

- Branch merged, issue `#N` closed, master pipeline ID, prod `short_hash`.
- Outcome review: agreed / ruled / pending (with the task link), follow-ups filed.
- Anything left behind and why.

End with `I'm done please delete me` on its own line only if every part is genuinely finished.
