## Why

The dream cycle's evaluator cuts every workflow definition to its first 2000 characters before
the LLM sees it. Most workflows are longer (Build Software is 10 KB), so the evaluation reasons
about routing, waits and safety steps it cannot see. On 30 Oct it reported "many workflow
definitions are truncated" as a key issue and raised #253, which asked for an async wait that
Build Software already has, past the cut. Closes #254.

## What Changes

- `workflow_evaluator` puts each definition in the prompt whole, never cut mid-file, up to a
  total `max_definition_chars` (default 120000).
- Order: workflows with failures in the period first, then low performers, then other workflows
  that ran, then the rest by name.
- Definitions that do not fit are listed by name under "Not shown", so the model knows they exist
  and that it has not seen them.
- The system prompt says the definitions shown are complete, and to make no claims about the
  content of workflows that were not shown.
- The evaluation output records `definitions_shown` and `definitions_omitted`.

## Capabilities

### New Capabilities
- `dream-workflow-evaluation`: what the dream cycle's evaluator is shown of each workflow.

### Modified Capabilities
<!-- None -->

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | The evaluator never sends a workflow definition cut mid-file | Unit tests on the prompt sent to the LLM: a 10 KB definition appears byte-for-byte; a definition one character over the whole budget is named under "Not shown" and none of it is sent; no `... (truncated)` marker in the evaluator source |
| O2 | When the definitions exceed the budget, the workflows that matter most are shown and the rest are named as not shown | Unit test: with a small budget, failing and low-performing workflows are shown before unused ones, a smaller one after an omitted one still fits, and every omitted name appears under "Not shown" and in `definitions_omitted` |
| O3 | The model is told the definitions it sees are complete and to make no claims about workflows it was not shown | Unit test on the system prompt / prompt text |
| O4 | In prod, the dream cycle's evaluation records that it saw the active workflows whole | The first prod dream cycle after deploy (rollout check, not a gate): its `evaluation.definitions_shown` includes every workflow that ran in the period, the log line gives shown/not-shown counts, and `key_issues` no longer says definitions are truncated |
