> Branch: `f235/commons-dream`. Commit with `Refs #235` (do not close #235).

## 1. Step

- [x] 1.1 `zebra_tasks/commons/dream.py` `CommonsDreamAction` (`commons_dream`): settings, off / stopped, never fails
- [x] 1.2 Offer candidates, filters, cap, start *Commons Offer* (entry `dream_cycle`), `proposed` record
- [x] 1.3 Gaps, keyword matching, import score, cap, daily budget from the ledger, background *Commons Import*
- [x] 1.4 Sharing promotion via `queue_promotion` (factored out of `propose_trust_promotion`)
- [x] 1.5 Report + voice lines; entry point; `COMMONS_INTERNAL_ACTIONS`

## 2. Wiring

- [x] 2.1 `dream_cycle.yaml` v10: `commons_dream` before the summary, Commons section in the prompt
- [x] 2.2 `/dreams/`: `dream_history.summarize_cycle` + template Commons block

## 3. Tests

- [x] 3.1 Unit: off / disabled / stopped / error, offer filters and cap, matching, threshold, budget, promotion
- [x] 3.2 In-memory E2E: offer → human task; trusted match → import started; untrusted → skipped
- [x] 3.3 Dream-cycle YAML tests, `/dreams/` page test

## 4. Docs

- [x] 4.1 CLAUDE.md settings, AGENTS files, `zebra-as-is.md`, `zebra-commons-design.md`

## 5. Review fixes

- [x] 5.1 `already_asked()`: a version already `public` is offered again only after a plain approval (decline / blocked = asked); a stopped publish offer journals `blocked`
- [x] 5.2 Promotion evidence reports declines (`sharing_approvals` → run, decided, declined)
