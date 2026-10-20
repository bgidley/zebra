## MODIFIED Requirements

### Requirement: Grouped navigation with a needs-you count
The app shell SHALL group navigation into core items (Dashboard, Tasks, Run Goal, Activity), an **Agent** group (Workflows, Knowledge, Dream Cycles) and a **Governance** group (Trust, Values Tags, and Ethics Audit for staff). The Tasks item SHALL link to the `/tasks/` inbox and SHALL show the number of inbox items (tasks waiting on a human), loaded from `/nav/needs-you/` after the page renders.

#### Scenario: Groups render in order
- **WHEN** a staff user loads any page that extends `base.html`
- **THEN** the nav shows the core items, then an "Agent" group, then a "Governance" group containing Ethics Audit

#### Scenario: Count shown when goals wait on you
- **WHEN** two running goals each have a READY human task and the browser requests `/nav/needs-you/`
- **THEN** the response shows the count 2

#### Scenario: Review-flagged tasks count
- **WHEN** one running goal has a READY human task and another has a task flagged for manual review
- **THEN** `/nav/needs-you/` shows the count 2

#### Scenario: No badge when nothing waits
- **WHEN** no running goal has a READY human task or a task flagged for manual review
- **THEN** `/nav/needs-you/` returns an empty badge

#### Scenario: Store failure does not break the page
- **WHEN** loading tasks raises an error
- **THEN** `/nav/needs-you/` returns HTTP 200 with an empty badge and the error is logged
