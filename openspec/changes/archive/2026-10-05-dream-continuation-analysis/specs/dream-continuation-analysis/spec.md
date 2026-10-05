## ADDED Requirements

### Requirement: Analyzer gathers continuation chains
The `metrics_analyzer` action SHALL gather continuation chains whose continuation runs started in the analysis window, and SHALL output a `continuation_analysis` block containing, per chain, the original workflow and goal, where the original run stopped (task states), each continuation's comment, assessor decision and rationale, and the final outcome.

#### Scenario: Seeded chain
- **WHEN** the metrics store holds a run of workflow A and a continuation run extending it with a comment and decision
- **THEN** `continuation_analysis.total_continuations` is 1
- **AND** the chain lists workflow A as the original workflow, the comment, the decision, and the final run's success

#### Scenario: Lineage fields missing
- **WHEN** a continuation run has no comment, decision or rationale
- **THEN** the analysis still succeeds and reports those values as null

### Requirement: Continuation rate per workflow
Each `workflow_stats` entry SHALL include `continued_runs` and `continuation_rate` (continued runs divided by total runs in the window), computed in the analyzer.

#### Scenario: Half of runs continued
- **WHEN** workflow A has 4 runs in the window and 2 of them were continued
- **THEN** A's `continuation_rate` is 0.5 and `continued_runs` is 2

### Requirement: Continuation patterns and proposals
The analyzer SHALL report frequently continued workflows with their comments, capability gaps (continuations decided as `new_workflow`), and steps added after the fact, and SHALL produce targeted improvement proposals tagged `source: continuation`: extend a workflow continued at least `min_continuations_for_proposal` times, and promote a successful workflow used for a `new_workflow` continuation.

#### Scenario: Frequently continued workflow
- **WHEN** workflow A was continued twice into workflow B, which ran a step A lacks
- **THEN** A appears in `frequently_continued` and the step appears in `added_steps`
- **AND** there is an `enhance` proposal targeting A that mentions the added step

#### Scenario: Missing capability
- **WHEN** a continuation was decided as `new_workflow` and its run succeeded
- **THEN** it appears in `capability_gaps` and a promote proposal targets the continuation's workflow

### Requirement: Proposals reach the optimizer
The `workflow_evaluator` SHALL include continuation findings in its prompt and SHALL merge continuation proposals into `improvement_priorities` unless an equivalent (type, target) priority exists. The `workflow_optimizer` SHALL apply them through the existing generated-workflow validation and SHALL report them in `continuation_changes`.

#### Scenario: LLM omits continuation proposal
- **WHEN** the evaluator LLM returns no priority for a continued workflow
- **THEN** the evaluation still contains the continuation `enhance` priority

#### Scenario: Optimizer applies continuation proposal
- **WHEN** the optimizer modifies a workflow from a continuation priority and the YAML is valid
- **THEN** `continuation_changes` lists it with status `made`

#### Scenario: Invalid continuation change
- **WHEN** the optimizer's YAML for a continuation priority fails validation
- **THEN** it is not saved and `continuation_changes` lists it with status `failed`

### Requirement: Summary reports continuations
The dream-cycle summary prompt SHALL include a "Continuations" section with the continuation count, top continued workflows and continuation-driven changes.

#### Scenario: Summary prompt
- **WHEN** the dream cycle definition is loaded
- **THEN** the `generate_summary` prompt references the continuation count, top continued workflows and `continuation_changes`

### Requirement: Graceful degradation
Continuation analysis SHALL NOT fail the dream cycle when the store cannot provide lineage or there are no continuations; it SHALL log and return an empty `continuation_analysis`.

#### Scenario: No continuations
- **WHEN** no run in the window has `extends_run_id`
- **THEN** `continuation_analysis.total_continuations` is 0, proposals are empty, and every `continuation_rate` is 0

#### Scenario: Store lacks lineage queries
- **WHEN** `get_continuations_since` raises
- **THEN** the analyzer logs a warning and still returns the rest of the analysis
