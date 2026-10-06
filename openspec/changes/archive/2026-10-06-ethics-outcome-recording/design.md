## Context

Every gate decision (`ethics_gate` input/plan, `record_dilemma_resolution`) is already appended to the `EthicsAuditStore`. What is missing is (a) persistence of the post-execution review and (b) a per-run record of *why* a run was rejected that `AgentLoop` and the UI can read.

## Goals / Non-Goals

**Goals:** post-review verdict audited and visible; rejection reason surfaced in `AgentResult` and run pages; memory update independent of the review.

**Non-Goals:** routing on the post-review verdict (still advisory); writing a metrics `WorkflowRun` for rejected goals (would skew per-workflow success rates — no workflow ran); fixing the general "failed task stops the branch" behaviour (#140).

## Decisions

- **Keep the review prompt in YAML as `llm_call`** and add a separate recorder action, rather than a bespoke LLM action. The prompt stays editable; the recorder is deterministic and testable.
- **Reorder the tail** instead of adding error routes: `update_conceptual_memory` moves before the review. `llm_call` with `response_format: json` returns raw text on parse failure, so the recorder treats non-dict output as "unparseable" (`approved=False`, fail-closed, consistent with `ethics_gate` #118).
- **Rejection gate inference** from process properties, in priority order: `dilemma_resolution.route == "reject"` → `dilemma_resolution`; `ethics_plan_assessment.approved is False` → `plan_review`; else `input_gate`. The dilemma check comes first because the plan assessment is also present (escalated) on that path.
- **No audit write on rejection**: the gate already wrote one; a second entry would double-count rejections.
- Both actions degrade gracefully: missing audit store → warning; audit exception → logged; always `TaskResult.ok`.

## Risks / Trade-offs

- YAML reorder conflicts with any concurrent edit of the tail routings (#140 may touch `execute_workflow → assess_and_record`) — routing lines are distinct, so a textual merge is expected to be trivial.
- Post-review still costs one haiku call per goal; now justified by being recorded and displayed.
