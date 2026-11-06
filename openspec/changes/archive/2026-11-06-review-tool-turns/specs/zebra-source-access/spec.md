## ADDED Requirements

### Requirement: Globs support brace alternatives
Every `zebra_source` glob (list and search) SHALL accept `{a,b}` alternatives, nested or several
per pattern, matching a path when any expansion matches.

#### Scenario: Brace glob in search
- **WHEN** `zebra_source` searches with glob `zebra-tasks/tests/test_{zebra_source,launch}.py`
- **THEN** hits come from both files and from no other file

#### Scenario: Brace glob in list
- **WHEN** `zebra_source` lists with glob `zebra-agent/workflows/*_zebra_source.{yaml,yml}`
- **THEN** it returns the matching workflow files, not "No files match"

### Requirement: List accepts a glob as its path
When a list request has no `glob` and its `path` contains `*`, `?`, `[` or `{`, `zebra_source`
SHALL list the files matching `path` as a glob from the source root.

#### Scenario: Glob given as path
- **WHEN** `zebra_source` lists with path `zebra-tasks/tests/test_zebra_*.py` and no glob
- **THEN** it returns the matching test files instead of failing as a missing directory

### Requirement: Read Zebra Source reads the requested range
The built-in Read Zebra Source workflow SHALL pass `start_line` and `end_line` to `zebra_source`
so a read returns exactly the requested lines, and it SHALL carry a version above any dream copy
on prod, so it replaces that copy.

#### Scenario: Range read through the workflow
- **WHEN** Read Zebra Source runs with `start_line: 20` and `end_line: 25`
- **THEN** its result holds lines 20 to 25 and no others
