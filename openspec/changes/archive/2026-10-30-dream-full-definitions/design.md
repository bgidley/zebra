## Context

`WorkflowEvaluatorAction._build_prompt` appended every definition from `load_workflow_definitions`
cut to 2000 characters. The optimizer already uses full YAML when it modifies a workflow, and only
samples 500 characters as a style example when creating one, so the evaluator is the one place
where the cut changes what Zebra concludes.

## Decisions

- **Whole or not at all.** A partial YAML is what misled the model; a named omission is honest.
- **Budget, not unlimited.** Dream-made copies make the library grow; 120000 characters (about
  30k tokens) holds today's library with room, once per cycle on the medium tier. Overridable
  per task (`max_definition_chars`).
- **Relevance order from the metrics the evaluator already has**: `failure_patterns`
  (by failure count), `low_performers`, `workflow_stats` (by runs), then the rest by name. A
  definition that does not fit is skipped, and smaller ones after it can still fit.
- **Record what was shown** (`definitions_shown`, `definitions_omitted`) on the evaluation, so a
  later reader or outcome review can tell what the judgement was based on.

## Risks

- A bigger prompt costs more per cycle. It is bounded by the budget and runs once a day.
- If the library outgrows the budget, unused workflows go unseen. They are named, and the
  curator handles unused workflows anyway.
