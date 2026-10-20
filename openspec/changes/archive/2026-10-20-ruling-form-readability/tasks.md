Branch: `f215/ruling-form-readability`

## 1. Comparison output

- [x] 1.1 `compare_outcome_reviews`: `summary_markdown` (id, outcome text, verdicts, agreed) and sectioned `dispute_notes`
- [x] 1.2 Tests in `zebra-tasks/tests/test_outcome_review.py`

## 2. Form

- [x] 2.1 `human_task_form` honours `show_prior_outputs: false`; test in zebra-agent-web
- [x] 2.2 `{{key.field}}` schema defaults resolve (the ruling fields rendered empty); regression test
- [x] 2.3 Read-only markdown panels grow with content (no `max-h-96`)
- [x] 2.4 `outcome_review.yaml` v4: ruling form uses `summary_markdown` and hides prior outputs; workflow test
- [x] 2.5 Browser render of the #211 ruling (desktop 1440, phone 390): no `<pre>`, no inner scroll on desktop, no page overflow

## 3. Docs and checks

- [x] 3.1 `specs/outcome-review-design.md`, `specs/zebra-as-is.md`, `zebra-agent-web/AGENTS.md`, `zebra-tasks/AGENTS.md`
- [x] 3.2 Lint + format, unit suites; `openspec validate ruling-form-readability --strict`
