## MODIFIED Requirements

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
- **WHEN** a built-in workflow has been retired and the built-ins are copied at startup with the same or a lower version
- **THEN** the retired built-in is not copied back into the active library

## ADDED Requirements

### Requirement: A newer shipped built-in replaces stale copies
When the built-ins are copied at startup, a built-in whose shipped `version` is higher than its retired copy SHALL be installed, and the retired copy SHALL be renamed `<stem>.builtin-v<N>.yaml` so it stays retired without blocking later installs. Whenever a newer built-in version is installed (over a retired or an older active copy), every other active workflow file with the same name SHALL be retired with `superseded_by` set to that name. Copying the built-ins again SHALL change nothing.

#### Scenario: Built-in shipped over a dream copy
- **WHEN** built-in *Flow* v2 was retired in favour of dream copy `flow_1.yaml` v3 and the build ships *Flow* v3
- **THEN** `get_workflow("Flow")` loads the shipped built-in, `flow_1.yaml` is retired with `superseded_by: Flow`, and the old v2 file is `retired/flow.builtin-v2.yaml`

#### Scenario: Active built-in upgraded alongside a dream copy
- **WHEN** `flow.yaml` v2 is active with a newer dream copy `flow_1.yaml` and the build ships v3
- **THEN** `flow.yaml` is v3 and `flow_1.yaml` is retired

#### Scenario: Second startup is a no-op
- **WHEN** the built-ins are copied again after an upgrade
- **THEN** nothing is copied or retired

### Requirement: Shadowed built-ins are logged
At startup, a built-in that stays retired while another active file with its name is used in its place SHALL be logged as a warning naming the built-in, the active file and both versions.

#### Scenario: Dream copy still shadows the built-in
- **WHEN** built-in *Flow* v2 is retired, the build still ships v2, and `flow_1.yaml` v3 is active
- **THEN** startup logs one warning naming *Flow*, `flow_1.yaml`, v2 and v3
