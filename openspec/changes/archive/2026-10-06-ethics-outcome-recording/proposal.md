## Why

Two ethics paths in the Agent Main Loop produce no durable, visible outcome (GitLab #143):

1. `ethics_post_review` (an `llm_call`) writes `ethics_post_assessment`, but nothing reads it — not the UI, not the audit log, not routing. It also sits *before* `update_conceptual_memory`, so if the review call fails, the memory update is skipped.
2. `ethics_rejection` is a bare terminal task. `AgentLoop` reports the generic error "Workflow failed", losing which gate rejected and why; the run page shows no reason.

## What Changes

- New task action `record_ethics_review`: normalises `ethics_post_assessment` and appends an `EthicsAuditEntry` with `check_type="post_review"`.
- New task action `record_ethics_rejection` on the `ethics_rejection` task: identifies the rejecting gate (`input_gate`, `plan_review`, or `dilemma_resolution`) and stores `ethics_rejection = {gate, reasoning, concerns}` on the process. No new audit write — every gate verdict is already audited.
- `agent_main_loop.yaml` (v10): reorder the tail to `assess_and_record → update_conceptual_memory → ethics_post_review → record_ethics_review` so the memory update no longer depends on the review.
- `AgentResult` gains `ethics_rejection: dict | None`; `error` carries the rejection reason instead of "Workflow failed".
- Run detail / pending pages show an "Ethics" panel: rejection reason, or post-review verdict with concerns and recommendations.

## Capabilities

### New Capabilities
- `ethics-outcome-recording`: durable recording and surfacing of ethics rejections and post-execution reviews in the goal loop.

### Modified Capabilities
<!-- none: ethics-audit-trail's EthicsGateAction requirement is unchanged; post_review is an additional check_type. -->

## Impact

- `zebra-tasks`: two new actions + entry points.
- `zebra-agent`: `workflows/agent_main_loop.yaml`, `loop.py` (`AgentResult`).
- `zebra-agent-web`: `api/web_views.py`, new `partials/ethics_outcome.html`, run pages.
- No schema/migration changes (reuses `EthicsAuditEntry`).
