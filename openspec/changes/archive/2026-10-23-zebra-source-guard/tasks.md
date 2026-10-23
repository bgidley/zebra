## 1. Guard

- [x] 1.1 `resolve_source_path`: separate outside / sensitive / unknown-top-level; refusal messages say why
- [x] 1.2 Unknown top level that does not exist returns a missing path; an existing one is refused

## 2. Auto-recovery

- [x] 2.1 `confident_match()`: unique same-name file, else unique ≥ 0.9 close match
- [x] 2.2 `_read` reads the match with a correction note; output gains `path`
- [x] 2.3 `missing_path_message` adds suggestions for undeployed entries too

## 3. Docs and workflow

- [x] 3.1 *Read Zebra Source* version 3 description
- [x] 3.2 `zebra-tasks/AGENTS.md`, `specs/zebra-as-is.md`

## 4. Tests

- [x] 4.1 O1: typo, wrong directory, missing package prefix read with note and `output.path`
- [x] 4.2 O2: ambiguous / weak matches fail; never auto-reads hidden files
- [x] 4.3 O3: refusal reasons; existing non-allowlisted entry refused
