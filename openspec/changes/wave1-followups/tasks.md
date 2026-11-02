> Branch: `f267/wave1-followups`. Commits reference `Refs #267`, `Refs #268`, `Refs #270`.

## 1. Honest hints (#267)

- [x] 1.1 `claude_code_build` → `context_dependent`; add to `WRITERS`, drop from `REVERSIBLE_WRITERS`
- [x] 1.2 Test: strict gym mode refuses `claude_code_build`; no `always_reversible` module calls `submit_build`
- [x] 1.3 Git actions declare their own hint; `_GitAction` none; hint test checks `vars(cls)` only

## 2. Identity (#268)

- [x] 2.1 Subprocess restart test (npub, pubkeys, device chain)
- [x] 2.2 Commons-off test posts import and revoke too

## 3. Provenance (#270)

- [x] 3.1 Stamped workflow selected and run end to end
- [x] 3.2 Legacy (blockless) workflow selected and run
- [ ] 3.3 After deploy: read-only prod check for a workflow saved since 68516eb with a `commons` block; post on #270

## 4. Docs

- [x] 4.1 `specs/zebra-as-is.md`, `zebra-tasks/AGENTS.md`
