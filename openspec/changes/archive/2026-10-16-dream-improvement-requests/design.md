## Context

The dream cycle (`dream_cycle.yaml`) analyses metrics, curates and optimises workflows, and reviews knowledge. Its evaluator already spots problems the optimizer cannot fix with YAML, and the optimizer's `failed_changes` often fail because a needed action is not registered. These end up only in the summary text. Bug reports (#186) already established the "process + one human review task" pattern for things a human must triage.

## Goals / Non-Goals

**Goals:** turn code-level findings into a small number of reviewable requests; no noise (cap, dedupe, "no request is fine"); never break the cycle.

**Non-Goals:** filing GitLab issues automatically; implementing the change; per-user scoping (requests are about the system).

## Decisions

- **One process per request, human task for review.** Reuses the engine, the human-task inbox and the Bug Report shape; no new tables. Properties: `improvement` (`title`, `area`, `problem`, `evidence`, `suggested_change`, `impact`), `improvement_title`, `improvement_markdown`, `goal`, `source_process_id`, `__improvement_request__` (normalised title, dedupe marker). The dream cycle's `__user_id__` is copied when present.
- **Placement after `review_knowledge`.** All findings (evaluation, optimisation, curation) are available; the summary can report the requests.
- **Dedupe by normalised title** against every earlier *Zebra Improvement Request* process (any state), and the earlier titles are shown to the LLM so it can avoid near-duplicates. A rejected request is therefore not re-raised with the same title.
- **Cheap model.** `model: haiku` on the task; `max_requests: 2`; inputs clipped.
- **Nothing to analyse → no LLM call** (no key issues, gaps, rejected changes or priorities).
- **Verdicts**: `accepted`, `rejected`, `duplicate`, `later`, plus optional `issue_url` and `notes`. The verdict is the task output (`__task_output_review`).

## Risks / Trade-offs

- LLM may propose workflow-level fixes as code requests → prompt says to exclude anything a workflow edit can fix; the human review is the backstop.
- Dedupe by title is coarse → the earlier titles in the prompt catch most near-duplicates; cap limits damage.
