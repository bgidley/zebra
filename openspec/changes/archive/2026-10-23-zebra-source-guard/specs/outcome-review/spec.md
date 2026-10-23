## MODIFIED Requirements

### Requirement: Zebra reviews its own deployed source
The `zebra_source` action SHALL read files, search for regex matches and list directories within
the source root only, under allowlisted top-level entries, and SHALL refuse dot-entries,
`*.sqlite3` files and paths that resolve outside the root (including via `..` or symlinks). Listings
and path suggestions SHALL name only entries a read would allow. A refusal SHALL say whether the
path is outside the tree or a hidden, secret or runtime file. A read of a missing path with exactly
one high-confidence match SHALL read that file in the same run with a correction note. It SHALL
never write.

#### Scenario: Read a source file
- **WHEN** `zebra_source` reads `zebra-tasks/zebra_tasks/agent/stuck.py` with a line range
- **THEN** it returns those lines prefixed with line numbers, capped at `max_chars`

#### Scenario: Escape attempt
- **WHEN** the path is `../etc/passwd` or an absolute path outside the root
- **THEN** the task fails with no content and a message saying the path is outside the Zebra source tree

#### Scenario: Hidden or secret file
- **WHEN** the path is `.env`, under `.venv/`, a `*.sqlite3` file or under `tmp/`
- **THEN** the task fails with no content and a message saying it is a hidden, secret or runtime file Zebra never reads

#### Scenario: Search
- **WHEN** `zebra_source` searches for a regex under a glob
- **THEN** it returns at most `max_results` `path:line: text` hits from allowed files

#### Scenario: List a directory
- **WHEN** `zebra_source` lists `zebra-tasks` (or the root, when no path is given)
- **THEN** it returns that directory's allowed subdirectories, each with `/` and its file count, and its allowed files with their sizes

#### Scenario: List by glob
- **WHEN** `zebra_source` lists with a glob such as `zebra-tasks/**/*.py`
- **THEN** it returns at most `max_results` matching allowed file paths, using the same glob rules as search

#### Scenario: Missing file with one clear match
- **WHEN** `zebra_source` reads a path that does not exist and exactly one readable file has the same name, or none has the same name and exactly one path is at least 0.9 similar with a file name at least 0.85 similar
- **THEN** it reads that file, its text starts with a note naming the requested and the actual path, and `output.path` is the actual path

#### Scenario: Missing file
- **WHEN** `zebra_source` reads a path that does not exist and has no single high-confidence match
- **THEN** the task fails with a message naming up to 5 nearest existing source paths (files with the same name first) and saying to use the list or search tool

#### Scenario: Unknown top-level entry
- **WHEN** the path's top-level entry is not allowlisted and does not exist, e.g. `zebra_tasks/agent/stuck.py`
- **THEN** it is handled as a missing file, not refused

#### Scenario: Path under an entry that is not deployed
- **WHEN** the path's top-level entry is allowlisted but absent from the source root
- **THEN** the failure message names the top-level entries that are present

#### Scenario: Directory read
- **WHEN** `zebra_source` reads a path that is a directory
- **THEN** the task fails with a message containing that directory's listing
