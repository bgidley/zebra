## MODIFIED Requirements

### Requirement: Dashboard leads with what needs you
The dashboard SHALL show, before anything else, a "Needs you" strip listing the first five inbox items (tasks waiting on a human), each linking to that task, followed by a link to `/tasks/` with the number of further items when there are more than five. It SHALL omit the strip when nothing is waiting. It SHALL then show one vitals panel with spend today against the daily budget (with the paced allowance drawn as a band), the success rate, and the queue depth.

#### Scenario: A goal waits on you
- **WHEN** one running goal is waiting on human task `ht-1` and another is running normally
- **THEN** the Needs you strip appears above the vitals and lists only the waiting goal, linking to `/tasks/ht-1/`

#### Scenario: More than five waiting
- **WHEN** seven items are waiting
- **THEN** the strip lists five and links to `/tasks/` saying 2 more

#### Scenario: Budget bar
- **WHEN** the daily budget is $50, spend is $7.42 and the paced allowance is $31.11
- **THEN** the spend bar is 14.8% wide and the allowance band 62.2% wide

#### Scenario: Budget unavailable
- **WHEN** the budget manager is not available
- **THEN** the vitals panel says the budget is unavailable and the page still renders
