## Why

Review in the delivery cycle is thin. The only check is a Zebra feedback call before the closing
commit, and it sees the author's own bullet list rather than the code. Nothing records what a
feature was meant to achieve, so nothing checks whether it did. Closes #190.

## What Changes

- **Outcomes at the start.** Every non-trivial OpenSpec proposal gets an `## Outcomes` section with
  3–5 observable outcomes and how each will be checked. The outcomes are posted on the GitLab
  issue. There is no approval gate; the human sees them on the issue.
- **Outcome review after deploy.** A new *Outcome Review* Zebra workflow takes the outcomes, the
  merged diff and Claude's verdicts. Zebra reviews blind to Claude, reading its own deployed source
  through new read-only tools. The two sets of verdicts are compared. If they disagree, Zebra
  reconsiders once with Claude's evidence. If they still disagree, the workflow parks on a human
  task for a ruling.
- **Blocking.** A session may not sign off ("I'm done please delete me") while the review is
  waiting on a human. Outcomes agreed as partial or missed become follow-up issues.
- New `zebra_source` action and *Read Zebra Source* / *Search Zebra Source* tool workflows.
- New `compare_outcome_reviews` action.
- New `run_workflow` management command: run a named workflow with JSON inputs, or report the
  status of one already running.
- New `scripts/zebra-outcome-review.sh`. It replaces the diff-blind review before the closing
  commit; `zebra-feedback.sh` now reviews the outcomes at the start.
- CLAUDE.md, `/cicd`, `cicd-manager` and the OpenSpec proposal rules describe both steps.
  Trivial changes (docs-only, one-line fixes) skip them.

## Outcomes

| # | Outcome | How we'll know |
|---|---|---|
| O1 | Non-trivial features record 3–5 outcomes at the start and post them on the issue | OpenSpec proposal rule + CLAUDE.md step |
| O2 | Zebra reviews against the outcomes reading its deployed source (read-only, sandboxed), blind to Claude's verdicts | Workflow + `zebra_source` tests, including sandbox escapes |
| O3 | Agreement on every outcome completes the review with a reconciled table and no human input | Workflow test, agreed path |
| O4 | Disagreement after Zebra reconsiders parks on a human task; the script exits non-zero until it is ruled | Workflow test, disputed path; script exit codes |
| O5 | The process docs make both steps part of every session; trivial changes skip | Docs diff |

## Non-goals

- Simultaneous wall-clock review: Claude's verdicts are an input, and Zebra stays blind to them
  until the comparison.
- Fixing the other drift in `/cicd` and `cicd-manager` (worktree merges, polling); tracked separately.
- Write access to source for Zebra.

## Capabilities

### New Capabilities
- `outcome-review`: outcomes contract at feature start; dual Zebra + Claude review after deploy
  with escalation to a human.

### Modified Capabilities
<!-- none -->

## Impact

- `zebra-tasks`: two new actions plus entry points.
- `zebra-agent/workflows`: three new built-in workflows.
- `zebra-agent-web`: `run_workflow` command.
- `scripts/`, CLAUDE.md, `.claude/` process files, `openspec/config.yaml`.
- No data model or migration changes.
