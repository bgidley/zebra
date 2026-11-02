## Why

Slice A of #251 gave the host builder delivery stages (propose, ship, review, merge) with scoped
credentials, but nothing drives them: a GitLab issue still needs a host Claude session to become
a change, and Zebra's own judgement never reaches the human. Slice B adds the Zebra workflow that
runs Zebra's development process on its own code, with one human review of the GitHub PR showing
Zebra's recommendation. Part of #251.

## What Changes

- New system workflow **Improve Zebra** (`zebra-agent/workflows/improve_zebra.yaml`), input
  `issue` (+ optional `title`): `propose` stage → Zebra's outcome feedback (`llm_agent` over its
  own source) → `ship` stage → Zebra's recommendation (`llm_agent`, JSON: per-outcome verdicts,
  merge / changes / reject, markdown) → **one human task** `review_pr` (PR link, pipeline,
  sensitive files, recommendation; routes `merge` / `changes` / `reject`) → report. `changes`
  loops back to `ship` on the same branch with the reviewer's feedback; a stage that does not
  finish fails the process. Merge and the post-deploy outcome review are slice C.
- Builder: propose / ship results also carry `diff_excerpt` / `diff_truncated` from the same
  host-side compare call, redacted and capped, so the recommendation reviews the real diff.
- Dream cycle: a *Zebra Improvement Request* gains the verdict "Accept and let Zebra build it"
  (`build`). It files the issue like `accepted`, then `start_improvement_build` starts Improve
  Zebra for it (or for the issue the reviewer linked). Request workflow v3.
- System workflows are protected from the dream cycle: `load_workflow_definitions` leaves out
  every `system`-tagged workflow (not only the four core names), and the optimizer refuses a
  generated workflow named after a system workflow, which would otherwise shadow it.

## Capabilities

### New Capabilities
- `self-improvement-workflow`: Improve Zebra, its PR review, and system-workflow protection.

### Modified Capabilities
- `dream-improvement-requests`: the `build` verdict starts Improve Zebra.
- `claude-code-builder`: ship results carry the branch diff read on the host.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A GitLab issue goes propose → Zebra's outcome feedback → ship → Zebra's recommendation → PR review as Improve Zebra tasks, driving the builder's stages on one `f<issue>/improve-zebra` branch | Workflow test with a faked host builder: the spool gets a `propose` then a `ship` job for the issue's branch, the ship prompt carries the change and Zebra's feedback, the recommendation prompt carries the host-checked pipeline, files and diff; on prod the v1 workflow is installed and `run_workflow "Improve Zebra"` refuses to start without `issue` |
| O2 | The human gets one task per review round, showing the PR, the pipeline for the reviewed head, sensitive files and Zebra's per-outcome recommendation | Test: `review_pr` is the only human task in the workflow; its read-only fields resolve to the PR URL, `**success** <url>`, the sensitive files and the recommendation markdown; the pipeline is the builder's, for the head it recorded |
| O3 | Review decisions and failures end cleanly: `changes` re-ships the same branch with the feedback and is reviewed again, `reject` ends with no further builder job, an unfinished stage fails the process | Tests for each route (job count after reject) and for failed / over_budget / rejected / cancelled propose and ship |
| O4 | The dream cycle can neither modify nor shadow a system workflow | Tests: a `system`-tagged workflow is not loaded for the optimizer; a generated workflow named after one is rejected and not saved |
| O5 | An improvement request can be sent to Zebra to build in one choice | Tests: verdict `build` files the issue and starts Improve Zebra for it (or the linked issue); other verdicts start nothing; failures never fail the request; prod shows the option (request workflow v3) |

## Non-goals

- The merge stage, outcome review after deploy and comments on the issue (slice C).
- The first real end-to-end run on a dream-request issue (slice C dogfood).
- Refusing a second Improve Zebra run for the same issue (it resumes the same branch).

## Impact

`zebra-agent/workflows/improve_zebra.yaml` (new), `zebra_improvement_request.yaml` (v3),
`zebra_tasks/agent/improvements.py`, `load_definitions.py`, `curator.py`, `optimizer.py`,
`scripts/zebra_builder.py`, `zebra_agent_web/api/dream_history.py`, tests, specs.
