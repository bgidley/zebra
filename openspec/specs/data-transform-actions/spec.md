# data-transform-actions Specification

## Purpose
TBD - created by archiving change data-transform-actions. Update Purpose after archive.

## Requirements

### Requirement: CSV parsing action
The `parse_csv` action SHALL parse CSV text from `data` into rows. With `has_header` true (default) each row SHALL be a dict keyed by the header row; otherwise each row SHALL be a list of strings. It SHALL honour a one-character `delimiter`, stop after `max_rows` rows setting `truncated: true`, and output `rows`, `columns`, `count` and `truncated`, also stored under `output_key`.

#### Scenario: Header rows
- **WHEN** `data` is `"name,age\nAnn,30\nBob,41"`
- **THEN** the output `rows` is `[{"name": "Ann", "age": "30"}, {"name": "Bob", "age": "41"}]`, `columns` is `["name", "age"]` and `count` is 2

#### Scenario: Truncated
- **WHEN** the CSV has more data rows than `max_rows`
- **THEN** only `max_rows` rows are returned and `truncated` is true

#### Scenario: Not text
- **WHEN** `data` resolves to something other than a string, or is empty
- **THEN** the task fails with an error naming the problem

### Requirement: XML parsing action
The `parse_xml` action SHALL parse XML text from `data` into a JSON-serializable dict `{root_tag: value}`, where attributes become `@name` keys, non-blank text of an element with attributes or children becomes `#text`, a leaf without attributes becomes its text, repeated child tags become lists, and namespace URIs are dropped from tag and attribute names.

#### Scenario: Mapping
- **WHEN** `data` is `<feed><item id="1">A</item><item id="2">B</item><title>T</title></feed>`
- **THEN** the output `data` is `{"feed": {"item": [{"@id": "1", "#text": "A"}, {"@id": "2", "#text": "B"}], "title": "T"}}` and `root` is `"feed"`

#### Scenario: Hostile XML refused
- **WHEN** `data` contains a `<!DOCTYPE` or `<!ENTITY` declaration
- **THEN** the task fails without parsing the document

#### Scenario: Malformed XML
- **WHEN** `data` is not well-formed XML
- **THEN** the task fails with the parser's error

### Requirement: JSON transform action
The `transform_json` action SHALL take `data` (a value, a pure template, or a JSON string, which may be fenced or surrounded by prose) and apply, in this order, the optional steps `path`, `where`, `sort_by` (with `descending`), `limit` and `pick`, outputting `result` (and `count` when it is a list), also stored under `output_key`.

#### Scenario: Path selection
- **WHEN** `data` is `{"a": {"items": [{"name": "x"}, {"name": "y"}]}}` and `path` is `a.items[*].name`
- **THEN** `result` is `["x", "y"]`

#### Scenario: Missing path
- **WHEN** `path` names a key or index that does not exist
- **THEN** `result` is `null` and the task succeeds

#### Scenario: Filter, sort, limit, pick
- **WHEN** `data` is a list of dicts and `where`, `sort_by`, `descending`, `limit` and `pick` are set
- **THEN** the rows matching every `where` equality are sorted by `sort_by`, cut to `limit`, and reduced to the `pick` fields, in that order

#### Scenario: LLM reply string
- **WHEN** `data` is a string holding JSON inside a ```json code fence
- **THEN** the JSON is parsed and transformed

#### Scenario: Bad input
- **WHEN** `data` is a string that holds no JSON, or a list step is applied to a value that is not a list
- **THEN** the task fails with an error naming the problem

### Requirement: Data actions are pure and bounded
All three actions SHALL declare `reversibility_hint = "always_reversible"`, SHALL fail the task when text input exceeds the size cap, and SHALL only produce JSON-serializable output.

#### Scenario: Metadata
- **WHEN** the action metadata is inspected
- **THEN** `reversibility_hint` is `always_reversible` for `parse_csv`, `parse_xml` and `transform_json`

#### Scenario: Oversized input
- **WHEN** `data` text is longer than the cap
- **THEN** the task fails and nothing is stored
