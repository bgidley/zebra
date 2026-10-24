## ADDED Requirements

### Requirement: Recovery fails runs whose definition is gone
Startup recovery SHALL fail a RUNNING process whose workflow definition cannot be found, setting
an `__error__` that names the missing definition, instead of logging an error and leaving it
RUNNING to be retried on every restart. Other processes SHALL still be recovered (#227).

#### Scenario: Definition missing
- **WHEN** recovery finds a RUNNING process whose definition id is not in the store
- **THEN** the process is FAILED with an `__error__` naming that definition id, and the next recovery does not see it

#### Scenario: Other processes unaffected
- **WHEN** recovery finds one process with a missing definition and one with its definition present
- **THEN** the first is failed and the second is recovered as before
