> Branch: `f153/dream-knowledge-review`. Reference `#153` in commits.

## 1. Implementation

- [x] 1.1 `WorkflowRun.user_id`; set in `assess_and_record`; Django metrics store reads/writes it
- [x] 1.2 `review_knowledge` action: window, per-user gather (entries, runs, human answers, continuation comments)
- [x] 1.3 LLM proposal + validation; apply rules for new/update/stale/merge/reinforce by source
- [x] 1.4 Contradiction / verification proposals as workflows, no duplicates; `review_entry_ids` in `pick_entries_for_verification`
- [x] 1.5 Audit trail with before/after; `revert_knowledge_changes()`
- [x] 1.6 Entry point; `dream_cycle.yaml` v6 step + "Knowledge" summary section

## 2. Tests & docs

- [x] 2.1 Acceptance test with seeded runs/entries (adds fact, flags contradiction, lowers stale confidence, human entries unchanged, idle user no LLM call)
- [x] 2.2 Cutoff, degradation, invalid proposals, dedupe, cap, revert, verification-by-ids tests
- [x] 2.3 Dream cycle definition tests; Django `user_id` round-trip tests
- [x] 2.4 `specs/zebra-as-is.md`, package AGENTS docs
