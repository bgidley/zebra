## Why

Workflows routinely receive structured text — a CSV from `file_read`, an XML feed, a JSON reply from `llm_call` or `kagi_extract` — and today the only ways to reshape it are another LLM call (cost, non-determinism) or `python_exec` (LLM-written code in generated workflows, a reliability problem tracked in #220). Small deterministic data actions make these steps cheap, predictable and safe. Closes #66.

## What Changes

- New `parse_csv` action: CSV text → list of row dicts (or lists when `has_header: false`), with `columns`, `count` and a `truncated` flag past `max_rows`.
- New `parse_xml` action: XML text → nested JSON-serializable dict (attributes as `@name`, text as `#text`, repeated children as lists, namespaces stripped to local names). Documents with a DOCTYPE or entity declaration are refused, so entity-expansion attacks cannot run.
- New `transform_json` action: applies, in order, `path` (`a.b[0].c`, `items[*].name`), `where` (field equality), `sort_by` (+ `descending`), `limit` and `pick` to a value — a raw property, a `{{template}}`, or a JSON string (code fences and surrounding prose tolerated, so `llm_call` replies work directly).
- All three take their input via a pure `{{template}}` (structure kept) or a literal, store the result under `output_key`, declare `reversibility_hint = "always_reversible"`, cap input size, and fail the task (never crash) on bad input.

## Capabilities

### New Capabilities
- `data-transform-actions`: deterministic CSV, XML and JSON parsing/reshaping task actions.

### Modified Capabilities
<!-- None -->

## Non-goals

- Writing CSV/XML back out (serialisation), XPath/XSLT, full JSONPath/JMESPath syntax, arithmetic or aggregation (use `python_exec`).
- Reading files directly — compose with `file_read` (storage rule 10).
- Schema validation of the parsed data.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A workflow can turn CSV text into rows a later task uses, with no LLM or `python_exec` | Engine test: a `parse_csv` → `transform_json` → template-consuming task workflow completes and the last task sees the filtered row values; exact-row tests for header/headerless, delimiter, quoted comma and newline, ragged rows, BOM, blank/duplicate headers, `max_rows` truncation (and `== max_rows` not truncated) |
| O2 | XML parses into a predictable dict and hostile XML is refused | Tests: attributes, text, mixed content, repeated children and namespaces (including a colliding `a:x`/`b:x`) map as specified; a billion-laughs document, an external DTD and an external entity fail the task before parsing; malformed XML fails with the parser error |
| O3 | JSON can be selected, filtered, sorted, limited and picked deterministically, including straight from an LLM reply | Tests: each step alone and combined in the specified order; `[*]` wildcard; `where` on a missing field; numeric, text, mixed-type, null and stable sorting; a fenced ```json reply string parses; a missing path yields `null` rather than an exception; bad input (non-JSON string, `where` on a non-list, malformed path) fails cleanly |
| O4 | The actions are safe to use anywhere | All three are registered entry points with `always_reversible` (pure: no I/O, no side effects); input over the size cap fails the task with nothing stored; every output is JSON-serializable (`set_process_property` succeeds) |
| O5 | They are live on prod and visible to workflow generation | After deploy, the prod container's action registry lists `parse_csv`, `parse_xml`, `transform_json` with their descriptions |

## Impact

- New package `zebra-tasks/zebra_tasks/data/`, three entry points, tests in `zebra-tasks/tests/data/`.
- No new dependencies (stdlib `csv`, `xml.etree.ElementTree`, `json`).
- Docs: `zebra-tasks/AGENTS.md`, `specs/zebra-as-is.md` action catalogue.
