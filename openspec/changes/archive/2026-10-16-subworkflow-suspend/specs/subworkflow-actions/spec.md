## ADDED Requirements

### Requirement: Subworkflow actions suspend instead of polling
`subworkflow` with `wait: true`, `wait_subworkflow` and `parallel_subworkflows` SHALL return
`TaskResult.suspend` on their child process ids rather than polling them, and SHALL build their
result from `context.subflow_results` when re-run. The result for each child SHALL be
`{success: true, process_id, properties, output}` (output being the child's `__output__`) when it
completed and `{success: false, process_id, error}` when it failed.

#### Scenario: Child waits on a human task
- **WHEN** a `subworkflow` task's child parks on a manual task
- **THEN** the task is AWAITING_SUBFLOW, and once the manual task is completed and the child completes, the task completes with the child's `__output__` and the parent continues

#### Scenario: Child fails
- **WHEN** the child of a `subworkflow` or `wait_subworkflow` task fails
- **THEN** the task fails with the child's `__error__`

#### Scenario: Parallel results keep their keys
- **WHEN** `parallel_subworkflows` runs workflows with keys `a` and `b` and `b`'s child fails
- **THEN** the task completes with results keyed `a` and `b` and routes `partial_failure`

### Requirement: Timeout bounds the child's inline run
The `timeout` property of `subworkflow` and `parallel_subworkflows` SHALL bound each child's
inline auto-task chain via `start_process_with_timeout`; a child still running its chain after
`timeout` seconds is failed. Time a child is parked on a manual task SHALL NOT count.

#### Scenario: Slow child
- **WHEN** a `subworkflow` task with `timeout: 0.2` starts a child whose action runs for 5s
- **THEN** the child is failed with a "Timed out" error and the task fails with it

### Requirement: wait_subworkflow waits only for its own children
`wait_subworkflow` SHALL suspend on the given process only when it is a child of the task's
process, and SHALL fail otherwise. Its `timeout` property SHALL be ignored with a warning.

#### Scenario: Wait on a child spawned without waiting
- **WHEN** a `subworkflow` task with `wait: false` starts a child that parks on a manual task, and a later `wait_subworkflow` task waits on it
- **THEN** the waiting task resumes and completes with the child's output once the child completes

#### Scenario: Not a child
- **WHEN** `wait_subworkflow` is given the id of a process whose parent is another process
- **THEN** the task fails and nothing is suspended

### Requirement: fail_fast stops starting children
With `fail_fast: true`, `parallel_subworkflows` SHALL NOT start further children once a started
child has failed, and SHALL fail immediately when a workflow config has no definition.

#### Scenario: First child fails during its inline run
- **WHEN** the first of two children fails while starting and `fail_fast` is true
- **THEN** the second child is never created and the task's results hold only the first
