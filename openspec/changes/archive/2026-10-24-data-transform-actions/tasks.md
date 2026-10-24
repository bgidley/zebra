> Branch: `f66/data-transforms`. Reference `#66` in commits.

## 1. Implementation

- [x] 1.1 `zebra_tasks/data/_common.py` — `input_value()` (resolve_raw + size cap), `input_text()`
- [x] 1.2 `zebra_tasks/data/csv_parse.py` — `ParseCsvAction`
- [x] 1.3 `zebra_tasks/data/xml_parse.py` — `ParseXmlAction` (DOCTYPE/ENTITY refusal, xmltodict-like mapping)
- [x] 1.4 `zebra_tasks/data/json_transform.py` — `TransformJsonAction` (path/where/sort_by/limit/pick)
- [x] 1.5 Register `parse_csv` / `parse_xml` / `transform_json` entry points; `uv sync --all-packages`

## 2. Tests

- [x] 2.1 CSV: header, headerless, delimiter, ragged rows, truncation, non-string / empty / oversized input
- [x] 2.2 XML: mapping, namespaces, billion laughs + DOCTYPE refused, malformed
- [x] 2.3 JSON: each step, combined order, wildcard, missing path, fenced LLM reply, bad input
- [x] 2.4 Engine workflow: `parse_csv` → `transform_json` → downstream template sees the values
- [x] 2.5 Metadata: reversible hint, entry points; lint + format

## 3. Docs & delivery

- [x] 3.1 `zebra-tasks/AGENTS.md`, `specs/zebra-as-is.md` catalogue
- [ ] 3.2 Zebra feedback; push; green pipeline; merge; archive this change; outcome review
