# Design

## Two actions, not one
Extraction (LLM, read-only) and storage (store writes, process spawning) are separate actions:
- `extract_knowledge` takes plain text inputs and returns candidates. #153 (dream-cycle knowledge
  review) can reuse it without inheriting main-loop storage rules.
- `store_learned_knowledge` re-validates its input, so any caller's candidates get the same
  category, key and secret checks.

The YAML cannot loop over candidates, so storage calls `store_knowledge_entry()` (the core of
`add_knowledge`, extracted from `AddKnowledgeAction.run`) once per candidate, rather than running a
task per candidate.

## Confidence
Stored confidence is `min(llm_confidence, max_confidence)`, with `max_confidence` 0.5 in the loop:
- that is below `knowledge_verification`'s 0.6 threshold, so agent facts appear in the weekly
  verification;
- `min_confidence` 0.5 drops weak guesses before they are stored;
- a same-value re-observation keeps `max(old, new)`, so the agent alone never reaches 1.0;
- confidence 1.0 comes only from a human: **Confirm** on `/knowledge/`, the verification
  workflow, or choosing `use_new` in a contradiction.

## Contradictions
Any conflicting value starts a *Resolve Knowledge Contradiction* process, whether the existing
entry is human or agent. The process:
- is a top-level process carrying `__user_id__` and the existing contradiction properties
  (`entry_id`, `category`, `key`, `existing_value`, `proposed_value`);
- is started at once, so its human task appears on `/tasks/`;
- is not a child of the main loop, so the goal still completes.

A `__knowledge_contradiction__ = "<entry_id>:<proposed_value>"` marker on the process prevents a
duplicate while the same conflict is still RUNNING.

## User inputs
`execute_goal_workflow` reads the child's `__task_output_<id>` for every `auto: false` task and
drops schema fields marked `readOnly`, which are values the workflow showed rather than ones the
user typed. The result is `execution_result.user_inputs`. Human tasks in grandchild processes are
not collected.

## Privacy
- The prompt excludes facts about the world, one-off task details and credentials.
- The prompt asks the LLM to flag special-category data as `sensitive`.
- Regexes drop password, API-key, token and card-number values whatever the opt-in.
- There is no per-user opt-in yet. `allow_sensitive` (task property) and the env var
  `ZEBRA_KNOWLEDGE_ALLOW_SENSITIVE` are deployment-wide switches.

## Risks
- LLM false positives: low stored confidence, verification, Confirm/Delete on `/knowledge/`.
- Contradiction spam: per-run cap of 5, and duplicate pending conflicts are suppressed.
- Cost: one haiku call per goal run that has a user and user text.
