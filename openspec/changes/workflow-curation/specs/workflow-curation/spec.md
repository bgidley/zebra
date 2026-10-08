## ADDED Requirements

### Requirement: Retired workflows are hidden but still loadable
`WorkflowLibrary.retire` SHALL move a workflow out of the active library, recording a reason, a timestamp and an optional `superseded_by`. A retired workflow SHALL NOT appear in `list_workflows`. `get_workflow` and `get_workflow_yaml` SHALL still return it, with its original YAML unchanged.

#### Scenario: Retire hides a workflow from selection
- **WHEN** a workflow is retired
- **THEN** `list_workflows` no longer includes it, and `get_workflow(name)` still loads it

#### Scenario: Restore returns a workflow
- **WHEN** a retired workflow is restored and no active workflow has its name
- **THEN** it is listed again and its YAML equals the original text

#### Scenario: Restore refuses a name clash
- **WHEN** an active workflow already has the retired workflow's name
- **THEN** `restore` raises and nothing changes

#### Scenario: Built-ins are not resurrected
- **WHEN** a built-in workflow has been retired and the built-ins are copied at startup
- **THEN** the retired built-in is not copied back into the active library

### Requirement: LLM-written workflows are tagged
Workflows saved by the workflow creator, the variant creator and the optimizer's create path SHALL carry the tag `llm-defined`. A modified workflow SHALL keep the provenance of the workflow it modifies.

#### Scenario: Optimizer modifies a hand-written workflow
- **WHEN** the optimizer saves a modified version of a workflow that has no `llm-defined` tag
- **THEN** the saved file has no `llm-defined` tag

### Requirement: Dream cycle retires stale workflows
The dream cycle SHALL run `workflow_curator` before loading workflows for evaluation. The curator SHALL retire:
- broken workflows (the definition fails to load or validate);
- older copies of a workflow that has a newer same-name file;
- failing workflows (`total_runs >= min_runs` and `success_rate < min_success_rate`);
- `llm-defined` workflows with no run within `unused_days`, or, if never run, not modified within `unused_days`;
- the weaker of two LLM-judged duplicates, when that weaker workflow is `llm-defined`.

#### Scenario: Failing workflow
- **WHEN** a workflow has 10 runs at 10% success and `min_success_rate` is 0.3
- **THEN** it is retired with rule `failing`

#### Scenario: Hand-written workflow is never retired for being unused
- **WHEN** a workflow without the `llm-defined` tag has not been used for a year
- **THEN** it is not retired

#### Scenario: Duplicate keeps the stronger workflow
- **WHEN** the LLM reports two `llm-defined` workflows as duplicates
- **THEN** the one with the lower success rate is retired with `superseded_by` set to the other

### Requirement: Curation is bounded, protected and auditable
The curator SHALL never retire workflows tagged `system` or the core system workflows. It SHALL retire at most `max_retire` workflows per cycle and report the rest as deferred. In dry-run mode it SHALL retire nothing. It SHALL store a JSON-serializable report (`retired`, `deferred`, `dry_run`) of every decision, with rule, reason, stats and `superseded_by`, which the dream-cycle summary includes.

#### Scenario: Per-cycle cap
- **WHEN** four workflows qualify and `max_retire` is 2
- **THEN** two are retired and two are reported as deferred

#### Scenario: Dry run
- **WHEN** dry run is enabled
- **THEN** decisions are reported with `applied: false` and the library is unchanged

### Requirement: Retired workflows are visible and restorable in the web UI
The workflow library page SHALL list retired workflows with their reason, date and replacement, each with a Restore action. The workflow detail page SHALL offer Retire for active workflows, and SHALL show a retired banner with Restore for retired ones.

#### Scenario: Restore from the library page
- **WHEN** a user restores a retired workflow from the library page
- **THEN** it returns to the active library
