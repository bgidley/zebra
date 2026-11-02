# Self-improvement: Zebra delivers changes to its own code

Issue: #251 (epic). OpenSpec: `openspec/specs/self-improvement-workflow/spec.md` (slice B, change
`improve-zebra-workflow`); builder stages: [claude-code-builder-design.md](claude-code-builder-design.md) §7
(slice A).

## 1. Goal & scope

A change to Zebra's own code goes through Zebra's development process (CLAUDE.md) as a Zebra
workflow, not a host Claude session: issue → OpenSpec proposal with outcomes → Zebra's outcome
feedback → implementation + CI → GitHub PR → **one human review** with Zebra's recommendation.
Claude Code does the work in the host builder's sandbox; Zebra orchestrates, judges and gates.

| Slice | What | State |
|---|---|---|
| A | Builder delivery stages (`propose` / `ship` / `review` / `merge`) with per-stage credentials, merge bound to the approved head, host-checked results | Shipped (`41c0c56`) |
| B | *Improve Zebra* workflow up to the PR review; `build` verdict on dream requests; system workflows off-limits to the dream cycle | This change |
| C | Merge stage after approval, deploy check, outcome review (review stage + *Outcome Review*), issue comments; first real run on a dream-request issue | Next |

Not in scope: egress filtering for the sandbox; more than one build at a time.

## 2. Data model

No tables. Process properties of *Improve Zebra*: inputs `issue`, `title`; `propose_job`,
`ship_job` (job records), `__task_output_await_propose` / `__task_output_await_ship` (builder
results: `report`, `head_sha`, `changed_files`, `sensitive_files`, `pipeline`, `diff_excerpt`),
`outcome_feedback` (text), `recommendation` (`{verdicts, recommendation, reasons, markdown}`),
`__task_output_review_pr` (`{feedback}`), `answer`. Request workflow v3 adds `improvement_build`.

## 3. Interfaces

- Workflow `Improve Zebra` (`zebra-agent/workflows/improve_zebra.yaml`, `system`,
  `inputs.required: [issue]`): never selected for a goal. Start it with
  `manage.py run_workflow "Improve Zebra"` (input `{"issue": "N"}`) or from a dream request.
- Action `start_improvement_build` (`zebra_tasks/agent/improvements.py`).
- `zebra_tasks.agent.load_definitions`: `is_system_workflow(name, tags)`,
  `is_system_workflow_name(library, name)`.

## 4. Control flow

```
propose ─▶ await_propose ─done─▶ outcome_feedback ─▶ ship ─▶ await_ship ─done─▶ recommend ─▶ review_pr
                 └─failed/over_budget/rejected/cancelled─▶ stage_failed ◀──────────┘          │
                                                         ship ◀── changes (feedback) ─────────┤
                                                       report ◀── merge / reject ─────────────┘
```

- Branch `f<issue>/improve-zebra` for every stage, so `changes` and reruns resume it.
- `recommend` uses host-checked facts only; never `merge` unless the pipeline is `success`.
- Dream request: `review → file_issue → start_build`. `start_build` starts Improve Zebra (unlinked,
  started at once, as request processes are) only for verdict `build` with a filed or linked
  issue; otherwise it records a skip. It never fails the request.
- Dream cycle protection: `load_workflow_definitions` skips `system`-tagged workflows (so the
  optimizer never modifies them) and the optimizer rejects a generated workflow named after one
  (it would shadow the built-in). The curator uses the same rule.

## 5. Configuration

None new. The builder's stage tokens and ceilings (§5 of the builder design) apply; ship runs at
the ceilings (200 turns / 90 min).

## 6. Risks / open questions

- The recommendation is an LLM judgement on a capped diff; the PR review is the real gate.
- Claude Code subscription limits: a ship stage waiting on CI is long-running.
- Two runs for one issue share a branch; not prevented yet.
- Until slice C an approved PR is merged by hand; `merge` only records the approval.
- A failed recommendation step fails the process after the build; the PR stays open for a
  manual review.
