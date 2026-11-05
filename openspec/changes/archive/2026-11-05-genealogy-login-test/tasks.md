## 1. Login regression test (#274)

- [x] 1.1 Add `test_pages_are_behind_login` (real prod middleware stack, genealogy + commons, anonymous 302 / logged-in 200) replacing the attribute-only test
- [x] 1.2 Check by hand that exempting the view or dropping the middleware makes it fail
- [x] 1.3 Update `specs/zebra-as-is.md` and `zebra-agent-web/AGENTS.md`

## 2. Prod stamped-run check (#273)

- [x] 2.1 Read-only prod query: WorkflowRunModel runs since 68516eb whose workflow file has `commons.content_sha256`, and their success
- [x] 2.2 Post the evidence on #273; close it only if a stamped run succeeded

## 3. Delivery

- [x] 3.1 Outcomes posted on #274 and Zebra feedback run
- [ ] 3.2 ruff check/format, commit `Refs #274`, push, branch pipeline green
