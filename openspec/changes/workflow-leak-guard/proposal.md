## Why

LLM-written workflows can hard-code details from the runs the LLM was shown. The dream-cycle
evaluator prompt includes raw sample failed goals and continuation comments; its findings feed the
optimizer, which has no "don't copy run content" rule. So "update the Acme migration plan for Jane"
can become a hard-coded "check Acme's SLA with Jane" step in a library workflow. The creator and
variant creator have the same exposure through the goal and previous-run context. Customer and
personal details belong in run data, not in reusable workflows, and this is the first line of
defence before any skill sharing (Zebra Commons S3b/S4, #236/#231). Closes #237.

## What Changes

- New `zebra_tasks/agent/leak_guard.py`: `LeakGuard` checks the string literals (values and keys)
  a writer *added* to a workflow, compared with its parent, against the untrusted texts the writer
  was shown (its **exposure set**). It reports `LeakHit`s for: run phrases (normalised word
  n-grams, ≥ 4 tokens), long verbatim copies of the writer's own goal (≥ 8 tokens), and names
  (capitalised, not sentence-initial, not all-caps acronyms), emails, URL/email domains and numbers
  (≥ 3 digits) from the exposure set. Anything in the parent, in `{{templates}}`, or in the
  writer's own system prompt and action list is allowed.
- Every LLM workflow writer runs it before saving: `workflow_creator` (also used by
  `define_workflow`), `workflow_variant_creator` and `workflow_optimizer` (create and modify, before
  the golden-gym staging). On a hit it regenerates exactly once with "generalise these specifics
  into `{{goal}}` or task inputs". If hits remain, the dream-cycle optimizer rejects the change and
  saves nothing; the creator and variant creator keep the rewrite and record the hits, so a user's
  goal never fails over its own words (the issue said "reject" for every writer; see design).
  A crashing check fails closed in the optimizer.
- The evaluator records the run texts it was shown (`run_exposure`: sample failed goals, error
  types, continuation comments, capability-gap comments) so the optimizer can check against them.
- Writer prompts gain the rule "never copy goals, names, numbers or outputs from runs into the
  YAML" (the optimizer had none; the creator had it only after truncation).
- Rejections are recorded in the optimizer's `failed_changes` with `leak_hits`, so the dream-cycle
  summary and the dream-cycle page list them. Outputs and changes carry a `leak_guard` record
  (`generalised` / `kept` / `rejected` / `error` + hits).

## Capabilities

### New Capabilities
- `workflow-leak-guard`: run-content leak check for LLM-written workflows, with generalise-or-reject.

### Modified Capabilities
<!-- None: writer behaviour changes are captured by the new capability's requirements. -->

## Non-goals

- Paraphrase detection ("the bank client" for "Acme"): later layers (confidentiality/sensitivity
  LLM checks, `tainted_by`, human diff review) belong to the Commons slices.
- The `commons:` provenance block, `tainted_by` and moving the check into `WorkflowLibrary.save()`
  (S2, #229).
- Scanning hand-written workflows or workflows already in the library.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Literal specifics a writer was shown (names, emails, domains, numbers ≥ 3 digits, run phrases ≥ 4 tokens, goal copies ≥ 8 tokens) do not reach a saved or staged dream-cycle workflow | Unit tests per detector plus negatives (parent text, templates, system-prompt words, sentence-initial words, acronyms); optimizer test: sample failed goals naming "Acme Corp" and "Jane Smith", a first reply that hard-codes them, a generalised second reply → the saved and the gym-staged YAML contain neither. Paraphrase is out of scope |
| O2 | A dream-cycle change that keeps copying is rejected without touching storage, and the rejection is visible | Tests: two copying replies → exactly one regeneration, a `failed_changes` entry with `leak_hits`, the library directory and `pending_gym` unchanged; a crashing check rejects (fails closed); the dream-cycle page shows the leak hits; the summary prompt already lists `failed_changes` |
| O3 | Legitimate workflows pass first time, and a user's goal is never failed by the guard | Tests with one LLM call and no regeneration: creator ("plan a birthday party"), variant (names already in its source), optimizer (a clean fix, acronyms like SLA); creator/variant with persistent goal specifics → task succeeds, `leak_guard.status: kept`; existing creator, variant, optimizer and dream-cycle tests pass |
| O4 | Every LLM workflow writer applies the guard and states the rule | Tests drive each entry point (creator, variant creator, optimizer create and modify, gym staging) through a copying reply and see a regeneration listing the hits; each writer's prompt contains the "never copy" rule; `define_workflow` runs `workflow_creator` |
| O5 | Live on prod without disrupting the dream cycle | The deployed `zebra-web` image contains `leak_guard.py`; the next prod dream cycle after deploy completes, and its `optimization_results` changes and failures carry `leak_guard` / `leak_hits` fields when the guard fired |

## Impact

- New module `zebra-tasks/zebra_tasks/agent/leak_guard.py`; changes to `creator.py`,
  `variant_creator.py`, `optimizer.py`, `evaluator.py`; dream-cycle page shows leak hits.
- No new dependencies. No data-model or YAML schema change; no new settings.
- Docs: `zebra-tasks/AGENTS.md`, `specs/zebra-as-is.md`, `specs/zebra-commons-design.md` (leak-guard
  section marked shipped).
