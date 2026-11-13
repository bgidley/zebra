## 1. Outcomes

- [x] 1.1 Outcomes in the proposal, posted on #295, Zebra feedback taken (revised O1/O2, posted)

## 2. Ruling form

- [x] 2.1 `ruling_form()`: agreed line, per-outcome case + attributed pick + note, evidence last, `_inert()` text
- [x] 2.2 `compare_outcome_reviews` writes `ruling_form`, carries `briefs`; `change_line()` header
- [x] 2.3 `record_ruling()`: per-row `ruling`, follow-ups, `unruled`, Ruling column; free text kept

## 3. Brief

- [x] 3.1 `brief_outcome_disputes` (low tier, `complete_json`, never fails), entry point
- [x] 3.2 `parse_briefs()` + `TAKES_A_SIDE` guard; first-sentence fallback

## 4. Workflow and script

- [x] 4.1 *Outcome Review* v6: `compare_again` → `brief_disputes` → `human_ruling` (generated schema)
- [x] 4.2 `zebra-outcome-review.sh` asks to read the ruling only for `unruled` outcomes

## 5. Tests and checks

- [x] 5.1 Unit tests (form, guard, record, brief action), workflow tests (briefed + failed brief), script test
- [x] 5.2 Web test: page renders the crux and picks; submit refused without a pick, recorded with one
- [x] 5.3 Browser render of the real #279 ruling at 1280 / 390 px: no overflow, case then pick; submit completes `ruled`

## 6. Docs

- [x] 6.1 `specs/outcome-review-design.md`, `specs/zebra-as-is.md`, `zebra-tasks/AGENTS.md`
