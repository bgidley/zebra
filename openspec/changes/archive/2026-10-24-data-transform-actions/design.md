## Context

Task outputs land in process properties and are referenced by `{{templates}}`. `ExecutionContext.resolve_template` always returns a string (a dict becomes its Python `str()`), so data actions need the raw value: `zebra_tasks.knowledge.extract.resolve_raw` already returns the native value for a pure `{{a.b}}` reference. LLM replies are often JSON in a code fence; `zebra_tasks.llm.structured.parse_llm_json` already handles that.

## Decisions

- **One package, three actions** in `zebra_tasks/data/`: `parse_csv`, `parse_xml`, `transform_json`, sharing `_common.py` (`input_value()`, `MAX_INPUT_CHARS`). Each stores its result under `output_key` and returns it as the task output.
- **Input**: property `data` (literal or template). `resolve_raw` keeps structure for pure templates; text inputs over `MAX_INPUT_CHARS` (2,000,000) fail the task. `transform_json` parses a string input with `parse_llm_json`; the parsers require a string.
- **CSV**: stdlib `csv` on `io.StringIO`. `has_header` (default true) → list of dicts keyed by header, else list of lists. `delimiter` (default `,`, one character). `max_rows` (default 1000, hard cap 10,000) sets `truncated: true`. Short rows are padded with `""`, extra cells dropped, so every dict has the same keys. A leading BOM is dropped; blank header names become `column_N` and repeats get `_2`, `_3`, so no value is silently overwritten (from Zebra's outcome feedback). Values stay strings (no type guessing).
- **XML → dict** (xmltodict-like): a leaf element with no attributes is its text (or `null` if empty); otherwise a dict of `@attr` keys, child tags (a list when the tag repeats) and `#text` when non-blank. Tags and attributes are reduced to local names (`{ns}item` → `item`). The root is returned as `{root_tag: value}`.
- **Hostile XML**: refuse any input containing `<!DOCTYPE` or `<!ENTITY` (case-insensitive) before parsing. That removes entity expansion (billion laughs, external entities) without adding `defusedxml`; real-world feeds and API replies don't need DTDs.
- **transform_json pipeline**, fixed order: `path` → `where` → `sort_by` → `limit` → `pick`. Path syntax: dot-separated keys, `[n]` index (negative allowed), `[*]` maps the rest of the path over a list. Missing keys/indexes yield `null`, never an exception. `where` is a dict of `path: value` equality (all must match); `sort_by` is a path, stable, numeric when every non-null value is a number (CSV gives `"100"` and `"30"` as strings), `None` values last even when descending, mixed types fall back to comparing `str()`; `pick` is a list of paths, giving dicts keyed by the path string. `where`/`sort_by`/`limit`/`pick` on a non-list fail the task (except `pick` on a dict, which picks from it).
- **Always reversible**: all three are pure functions of their input.
- **Indexing after filtering** needs a second `transform_json` (`path: "[0].title"`), because `path` runs first to select the collection. Kept that way rather than adding a second path option.

## Risks

- Large data in process properties bloats the process row; caps bound it and `max_rows` lets workflows bound it further.
- XML single-vs-list ambiguity (one `<item>` is a dict, two are a list) is inherent to the mapping; `[*]` on a non-list treats it as a one-item list to soften this.
