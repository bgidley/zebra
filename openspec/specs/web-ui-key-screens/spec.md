# web-ui-key-screens Specification

## Purpose
TBD - created by archiving change web-ui-key-screens. Update Purpose after archive.

## Requirements

### Requirement: Dashboard leads with what needs you
The dashboard SHALL show, before anything else, a "Needs you" strip listing running goals that are waiting on a human task, each linking to that task, and SHALL omit the strip when none are waiting. It SHALL then show one vitals panel with spend today against the daily budget (with the paced allowance drawn as a band), the success rate, and the queue depth.

#### Scenario: A goal waits on you
- **WHEN** one running goal is waiting on human task `ht-1` and another is running normally
- **THEN** the Needs you strip appears above the vitals and lists only the waiting goal, linking to `/tasks/ht-1/`

#### Scenario: Budget bar
- **WHEN** the daily budget is $50, spend is $7.42 and the paced allowance is $31.11
- **THEN** the spend bar is 14.8% wide and the allowance band 62.2% wide

#### Scenario: Budget unavailable
- **WHEN** the budget manager is not available
- **THEN** the vitals panel says the budget is unavailable and the page still renders

### Requirement: Trust levels as one table
The Trust page SHALL list every domain in one table, each row a form posting `level` and `reason` to `/trust/<domain>/set/`, with the level chosen by a segmented control of radio inputs. The emergency override SHALL be an outline danger button that asks for confirmation and is not shown once Zebra is freed.

#### Scenario: Row form contract
- **WHEN** the Trust page lists the `code` domain at SEMI_AUTONOMOUS
- **THEN** its row posts to `/trust/code/set/` with radio inputs named `level` for each trust level, SEMI_AUTONOMOUS checked, and a `reason` field

#### Scenario: Freed
- **WHEN** Zebra has been freed
- **THEN** the emergency override button is not shown

### Requirement: Workflow detail shows structure before source
The workflow detail page SHALL show the workflow's steps, ordered along its routings from the first task (unreachable tasks last), and a structure diagram drawn at its natural width in a horizontally scrollable panel, before the YAML definition, which SHALL sit inside a collapsed disclosure. If the definition cannot be loaded or drawn, the page SHALL still render its stats and YAML.

#### Scenario: Step order
- **WHEN** a workflow routes gather to ask to merge and also defines an unreachable task
- **THEN** the steps read gather, ask, merge, then the unreachable task

#### Scenario: Definition fails to load
- **WHEN** the library cannot load the workflow definition
- **THEN** the page renders without steps or diagram

### Requirement: Run pages fit a phone
Run detail and pending-run pages SHALL NOT scroll horizontally at 390px wide; task panel headers SHALL truncate long names and hide the raw task id below the `sm` breakpoint.

#### Scenario: Phone width
- **WHEN** a run page is rendered at 390px wide
- **THEN** the document is no wider than the viewport
