> Branch: `f285/review-tool-turns`. `Part of #285` on interim commits, `Closes #285` on the last.

## 1. Source tools

- [x] 1.1 `zebra_source`: `expand_braces()` + any-of `_glob_match` (list and search), capped
- [x] 1.2 `zebra_source`: list treats a glob-like `path` (no `glob`) as a glob from the root
- [x] 1.3 Read Zebra Source v11 (v9 steps), List Zebra Source v4, Search Zebra Source v3 (glob syntax in descriptions)
- [x] 1.4 Tests: brace globs (list, search, nested), glob as path, range read through the workflow

## 2. Outcome review

- [x] 2.1 `zebra-outcome-review.sh`: `change_map` (files with +/- counts, test functions by file, capped) in the input
- [x] 2.2 Outcome Review v5: `change_map` input and prompt section; `max_tool_turns` 8 / 5; range and batching guidance
- [x] 2.3 Tests: script `change_map` (tests found, cut diff), workflow budget and prompt

## 3. Docs and delivery

- [x] 3.1 `specs/zebra-as-is.md` and `zebra-tasks/AGENTS.md` (`zebra_source` row)
- [ ] 3.2 ruff, unit tests; CI green; merge; verify prod runs Read v11 / List v4 / Search v3 / Outcome Review v5 and a range read
- [ ] 3.3 Outcome review (O5: compare input tokens with process `71a950e5`); archive the change
