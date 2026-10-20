## ADDED Requirements

### Requirement: Tasks inbox page
`/tasks/` SHALL render an inbox page (not a redirect) listing every item waiting on a human, oldest first: READY human (`auto: false`) tasks whose process is not COMPLETE or FAILED, and tasks flagged for manual review by recovery. Each row SHALL show the task name, its goal, its workflow and how long it has waited. A human row SHALL link to `/tasks/<task_id>/`. A review row SHALL offer Retry and Fail. The goal SHALL link to the run detail page when the item has a run, otherwise to the root process trace. When nothing is waiting the page SHALL say so.

#### Scenario: Only waiting items are listed
- **WHEN** one running goal waits on human task `ht-1`, another running goal has only an auto task in flight, and a third goal's task is flagged for manual review
- **THEN** `/tasks/` returns 200 and lists `ht-1` (linking to `/tasks/ht-1/`) and the flagged task (with Retry and Fail), and nothing for the second goal

#### Scenario: Oldest first
- **WHEN** two human tasks are waiting, created an hour apart
- **THEN** the older task is listed first

#### Scenario: Finished process
- **WHEN** a READY human task belongs to a process that is COMPLETE or FAILED
- **THEN** it is not listed

#### Scenario: Agent run over, process still waiting
- **WHEN** a goal's process is RUNNING with a READY human task but no in-progress run record
- **THEN** the task is listed

#### Scenario: Nothing waiting
- **WHEN** no item is waiting
- **THEN** the page shows an empty state saying nothing is waiting on you

#### Scenario: Store failure
- **WHEN** loading tasks raises an error
- **THEN** the page returns 200 with a message that tasks could not be loaded, and the error is logged

### Requirement: One source for what needs you
The inbox page, the nav needs-you badge and the dashboard Needs-you strip SHALL all be built from one read model (`inbox_items`), so their counts agree.

#### Scenario: Counts agree
- **WHEN** there is a mix of running goals with human tasks, finished processes with leftover READY tasks and review-flagged tasks
- **THEN** the badge count equals the number of inbox rows, which equals the number of items behind the dashboard strip
