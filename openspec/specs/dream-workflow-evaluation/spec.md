# dream-workflow-evaluation Specification

## Purpose
What the dream cycle's `workflow_evaluator` is shown of each workflow definition (#254).

## Requirements

### Requirement: The evaluator sees whole workflow definitions
The dream cycle's `workflow_evaluator` SHALL include each workflow definition it shows in full,
and SHALL NOT cut a definition part-way through.

#### Scenario: A long definition is shown whole
- **WHEN** a workflow definition is 10000 characters long and the budget allows it
- **THEN** the whole definition appears in the evaluation prompt, unchanged

### Requirement: Definitions are shown by relevance within a budget
The evaluator SHALL show definitions within a total of `max_definition_chars` characters
(default 120000), in this order: workflows with failures in the analysis period, then
low-performing workflows, then other workflows that ran, then the rest. Within each group, a
workflow with more runs or failures comes first. A definition that does not fit SHALL be named
in a "Not shown" list instead, and the evaluator SHALL continue with smaller definitions that
still fit.

#### Scenario: Over budget, the failing workflow is shown
- **WHEN** the definitions together exceed the budget and one workflow has failures
- **THEN** the failing workflow's definition is shown, an unused workflow that does not fit is
  named under "Not shown", and the output lists both in `definitions_shown` and
  `definitions_omitted`

#### Scenario: Everything fits
- **WHEN** all definitions fit in the budget
- **THEN** all are shown and `definitions_omitted` is empty

### Requirement: The model is told what it has and has not seen
The evaluator's instructions SHALL say that the definitions shown are complete and that the
model makes no claims about the content of workflows listed as not shown.

#### Scenario: Prompt states completeness
- **WHEN** the evaluator builds its prompt
- **THEN** the system prompt states the shown definitions are complete, and any "Not shown"
  list says those definitions were not provided
