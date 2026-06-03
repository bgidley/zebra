---
name: "CI/CD: Commit → Monitor → Fix → Merge"
description: Commit pending work, push, watch the GitLab pipeline, auto-fix failures, then merge to master and close the issue.
category: Workflow
tags: [cicd, gitlab, merge, automation]
---

Manage the complete CI/CD lifecycle for the current feature branch:
commit any pending code, push to GitLab, monitor the pipeline, attempt to fix failures, and — when green — merge to master and close the GitLab issue.

**Input**: Optional commit message override. If omitted, derive from branch name and staged diff.

---

## Step 1 — Orientation

Run these in parallel to understand current state:

```bash
git status
git branch --show-current
git log --oneline origin/master..HEAD
git diff --stat
```

Extract the **issue number** from the branch name:
- Pattern: `fN/description` → issue `#N`
- If no issue number is found, note that and skip the close step.

If already on `master`, stop and tell the user to work on a feature branch.

---

## Step 2 — Lint and format

**Always run before committing.** Fix any issues found:

```bash
uv run ruff check --fix .
uv run ruff format .
```

If `ruff check` cannot auto-fix (manual intervention needed), stop and report the errors.

---

## Step 3 — Commit pending changes

If there are unstaged or staged changes:

1. Stage only relevant source files (not `.env`, secrets, or large binaries):
   ```bash
   git add -u   # stage tracked modifications
   git status   # review what's staged
   ```
   For any genuinely new files that should be committed, add them explicitly by path.

2. Write a commit message following the project convention:
   - First line: `type: short description` (imperative, ≤72 chars)
   - If this is the final commit: `Closes #N` footer
   - Otherwise: `Refs #N`
   - Include `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` at the end

3. Commit using a HEREDOC:
   ```bash
   git commit -m "$(cat <<'EOF'
   <message>
   EOF
   )"
   ```

If there is nothing to commit (tree is clean), skip to Step 4.

---

## Step 4 — Push to GitLab

```bash
git push origin <branch>
```

Capture the push output. If the push is rejected (non-fast-forward), investigate before force-pushing — it may mean someone else pushed. Ask the user rather than force-pushing.

---

## Step 5 — Identify and watch the pipeline

```bash
glab ci list --repo gidley/zebra --per-page 1
```

Extract the pipeline ID from the output. Then poll until the pipeline reaches a terminal state (`passed` or `failed`). Use a background monitor loop:

```bash
until glab ci list --repo gidley/zebra --per-page 1 | grep -qE '(passed|failed).*#<pipeline-id>'; do sleep 15; done
glab ci list --repo gidley/zebra --per-page 1
```

While waiting, give the user a brief status update every few minutes.

---

## Step 6 — Handle pipeline outcome

### 6a — Pipeline passed → go to Step 7 (merge)

### 6b — Pipeline failed → enter fix loop

Keep a **fix attempt counter** (max 3). For each attempt:

**6b-i. Identify failing jobs**

```bash
glab ci list --repo gidley/zebra --per-page 1
```

Identify which stage failed (lint, test, e2e, pre-prod). Then trace the failing job:

```bash
glab ci trace --repo gidley/zebra <job-name> 2>&1 | tail -100
```

**6b-ii. Classify the failure**

| Failure type | Action |
|---|---|
| Ruff lint/format error | Fix the specific lines, re-run ruff, commit |
| Pytest assertion / import error | Read the failing test and source, fix the bug, commit |
| pre-prod container startup crash | Read Dockerfile and entrypoint.sh, fix, commit |
| pre-prod smoke test failure | Read smoke test output, check URLs/responses, fix test or app code |
| Infrastructure / network / external service | Cannot auto-fix — report to user and stop |
| Ambiguous | Read more context, ask the user if still unclear |

**6b-iii. Apply the fix**

- Read the relevant files before editing
- Make the minimal targeted change
- Re-run `uv run ruff check --fix . && uv run ruff format .`
- Run the relevant tests locally if fast:
  ```bash
  uv run pytest -x -m "not e2e and not smoke" --ds=zebra_agent_web.test_settings
  ```
- Commit the fix: `fix: <description of what was wrong>\n\nRefs #N`
- Push: `git push origin <branch>`
- Go back to Step 5 (watch new pipeline)

If the fix counter reaches 3 with no green pipeline, **stop and report** — summarise each attempted fix and the remaining failure, and ask the user how to proceed.

---

## Step 7 — Merge to master

Only execute this when the pipeline is **green**. Follow the exact workflow from CLAUDE.md:

```bash
git checkout master
git pull origin master
git merge --no-ff <branch> -m "Merge <branch> — Closes #<issue>"
git push origin master
git push github master
git branch -d <branch>
git push origin --delete <branch>
```

**Verify the deploy pipeline on master also passes** before declaring done:

```bash
glab ci list --repo gidley/zebra --per-page 1
```

Wait for it to reach `passed`. If it fails, checkout the branch again (`git checkout -b <branch>-hotfix master`) and apply a fix.

---

## Step 8 — Close the GitLab issue

If an issue number was found in Step 1:

```bash
glab issue close <N> --repo gidley/zebra
```

Then confirm:
```bash
glab issue view <N> --repo gidley/zebra
```

---

## Step 9 — Final report

Print a short summary:
- Branch merged: `<branch>`
- Issue closed: `#<N>` (or "no issue number found")
- Pipeline: link or ID
- Commits included: `git log --oneline master~<count>..master`

---

## Guardrails

- **Never force-push** without explicit user confirmation
- **Never skip hooks** (`--no-verify`)
- **Never push to master directly** — always go through the merge step above
- **Never commit `.env`, credentials, or secrets**
- **Max 3 fix attempts** before stopping and asking the user
- If any step produces unexpected output that looks like an infrastructure problem (runner down, Oracle unreachable, network timeout), stop immediately and report — do not retry
- If the branch has diverged from master during the fix loop, rebase cleanly before merging:
  ```bash
  git fetch origin master
  git rebase origin/master
  git push --force-with-lease origin <branch>
  ```
