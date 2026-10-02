### Requirement: Dashboard lists running goals
The dashboard SHALL show a Running Activities panel listing every top-level goal whose process is
in `RUNNING` state, oldest first, capped at 10. Each entry SHALL show the goal text, workflow name,
elapsed time since start, cost so far, and the names of tasks currently READY or RUNNING anywhere
in the goal's process tree. Each entry SHALL link to the run detail page when a `run_id` exists,
otherwise to `/activity/`. The dashboard SHALL also show a Running stat card with the count.

#### Scenario: Goal in progress
- **WHEN** a top-level process with `goal` "Write a haiku" is RUNNING with a RUNNING task
- **THEN** the dashboard panel lists "Write a haiku" with that task's name and its cost

#### Scenario: Sub-processes fold into their goal
- **WHEN** a RUNNING goal has a RUNNING child process
- **THEN** only one entry is shown, and it includes the child's in-flight tasks

#### Scenario: Stale child is ignored
- **WHEN** a RUNNING child process's parent is not RUNNING
- **THEN** no entry is shown for it

#### Scenario: Nothing running
- **WHEN** no top-level process is RUNNING
- **THEN** the panel shows "Nothing running"

### Requirement: Goals awaiting a human are flagged
A running goal with a READY task whose definition has `auto: false` (in the root or any running
sub-process) SHALL be marked "awaiting input" with a link to that task's form at `/tasks/<id>/`.

#### Scenario: Human task in child process
- **WHEN** a running goal's child process has a READY manual task `human-1`
- **THEN** the goal's entry shows "awaiting input" linking to `/tasks/human-1/`

### Requirement: Panel failure does not break the dashboard
If running activities cannot be loaded, the dashboard SHALL still render, showing the empty panel.

#### Scenario: Process store unavailable
- **WHEN** loading running processes raises an error
- **THEN** the dashboard returns HTTP 200 and the panel shows "Nothing running"
