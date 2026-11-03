> Branch: `f238/private-genealogy`. Reference `Refs #238` in commits.

## 1. Journal

- [ ] 1.1 `zebra_agent/genealogy.py`: `LineageJournal` (append / read, hit text dropped), reason normaliser
- [ ] 1.2 `WorkflowLibrary.save(reason=, leak=)` journals saved and rejected saves; `device` attribute; `refresh_owner` takes a 3-tuple
- [ ] 1.3 Web `resolve_commons_owner` returns the device label

## 2. Writers pass reasons

- [ ] 2.1 Optimizer (create, ungated modify) passes rationale + leak record
- [ ] 2.2 Gym promotion passes the candidate's reason + leak record
- [ ] 2.3 Creator / variant creator pass the selector's voice / reasoning

## 3. Genealogy model

- [ ] 3.1 `build_genealogy()`: files, hash closure, nodes, edges, hash-only ancestors, writer, diff, layers
- [ ] 3.2 Tests: chain of three, legacy / built-in / retired / hash-only, variant under another name

## 4. Page

- [ ] 4.1 View, URL, template, SVG layout (`api/genealogy_view.py`), link from the workflow page
- [ ] 4.2 View tests (render, 404, empty states, no reason recorded); theme test passes
- [ ] 4.3 Playwright container check: phone + desktop, light + dark

## 5. Docs

- [ ] 5.1 `specs/zebra-as-is.md`, `specs/zebra-commons-design.md`, package AGENTS.md files
