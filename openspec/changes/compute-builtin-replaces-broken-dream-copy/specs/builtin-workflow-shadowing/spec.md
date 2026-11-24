## ADDED Requirements

### Requirement: Built-in bump replaces a dream copy
The system SHALL, at startup, install a built-in workflow whose shipped version is higher than the active or retired copy of the same name, and retire the dream copies of that name.

#### Scenario: Dream rewrite of the built-in's file
- **WHEN** the active file is a dream v3, the retired built-in is v1, and the shipped built-in is v4
- **THEN** the library serves the shipped v4
