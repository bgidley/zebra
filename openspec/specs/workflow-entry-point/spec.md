# workflow-entry-point Specification

## Purpose
TBD - created by archiving change workflow-entry-point-flag. Update Purpose after archive.

## Requirements

### Requirement: Entry-point flag
A workflow definition MAY set top-level `entry_point: false`. Goal routing SHALL NOT offer such a
workflow as a candidate; a workflow without the key SHALL be offered as before.

#### Scenario: Hidden from the selector
- **WHEN** the library holds workflows A (`entry_point: false`) and B (no key)
- **THEN** `list_goal_workflows` returns B and not A

#### Scenario: Default is visible
- **WHEN** a workflow has no `entry_point` key
- **THEN** it is returned by `list_goal_workflows`

#### Scenario: Malformed value
- **WHEN** a workflow sets `entry_point: "false"` (a string)
- **THEN** a warning is logged and the workflow is treated as an entry point

### Requirement: Non-entry-point workflows stay callable
Setting `entry_point: false` SHALL NOT change loading, saving or execution by name.

#### Scenario: Dispatcher calls a hidden variant
- **WHEN** a dispatcher workflow runs a sub-workflow task naming a workflow with `entry_point: false`
- **THEN** the sub-workflow runs normally

#### Scenario: Save round-trip
- **WHEN** a workflow with `entry_point: false` is saved through `WorkflowLibrary.save()` and reloaded
- **THEN** it is still not an entry point
