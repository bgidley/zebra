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
- [x] 3.3 Read-only prod check for a workflow saved since 68516eb with a `commons` block, and its `content_sha256` recomputed; posted on #270 (2026-11-02: nothing saved yet, pending; 2026-11-03: prod at 608ec0f, the 03:05–03:07 UTC dream cycle saved three workflows, all three carry a `commons` block, and all three stored `content_sha256` values match a recompute)
- [ ] 3.4 Confirm whether a goal ran one of the three stamped workflows. **Pending**: no process for their definition ids is in the web log (from 2026-10-30) or the daemon log (from its 2026-11-03 21:41 restart). The daemon's 03:05–21:41 history is gone, and the authoritative `WorkflowRunModel` query on prod Oracle was not allowed from an agent session. Needs a human query (see #270).

## 4. Docs

- [x] 4.1 `specs/zebra-as-is.md`, `zebra-tasks/AGENTS.md`
