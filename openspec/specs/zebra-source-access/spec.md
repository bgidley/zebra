# zebra-source-access Specification

## Purpose
How Zebra's read-only source tools (`zebra_source` and the List, Read and Search Zebra Source
workflows) find, read and refuse paths, and how they report failures.

## Requirements

### Requirement: Source access failures carry a reason

Every failed `zebra_source` request SHALL fail the task with an error that starts with
`[<reason>] `, where `<reason>` is one of `protected`, `not_deployed`, `missing`, `invalid` or
`error`, and that ends with the list/search recovery hint.

#### Scenario: Protected path
- **WHEN** a caller reads a hidden, secret or runtime file, a path outside the source tree, or an
  existing top-level entry that is not allowlisted
- **THEN** the task fails with an error starting `[protected] `

#### Scenario: Path not deployed
- **WHEN** a caller reads or lists a path under an allowlisted top-level entry that is absent from
  the deployed tree
- **THEN** the task fails with an error starting `[not_deployed] `

#### Scenario: Missing path
- **WHEN** a caller reads or lists a path that does not exist and has no single clear match
- **THEN** the task fails with an error starting `[missing] `

#### Scenario: Bad request
- **WHEN** a caller gives no path or pattern, an invalid regex, a glob leaving the tree, a
  directory to read, a file to list, or a file over the size cap
- **THEN** the task fails with an error starting `[invalid] `

#### Scenario: Read error
- **WHEN** reading a file raises an `OSError`
- **THEN** the task fails with an error starting `[error] ` instead of raising

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
