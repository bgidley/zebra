## ADDED Requirements

### Requirement: Old workflow versions stay loadable after an upgrade

Installing a newer version of a built-in workflow SHALL NOT delete stored definitions of its
earlier versions, so a process pinned to an earlier version can still be shown and completed.

#### Scenario: Built-in workflow upgraded on startup
- **WHEN** the library has *Outcome Review* v3, the build ships v4, and `install_builtin_workflows` runs
- **THEN** the library file is v4 and the stored v3 definition still loads by its id

#### Scenario: Parked human task on the old version
- **WHEN** a process is parked on v3's `human_ruling` task and v4 has been installed
- **THEN** `/tasks/<id>/` renders the form from v3's definition
- **AND** completing the task finishes the process
