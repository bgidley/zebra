## Context

Design: `specs/zebra-commons-design.md` § Workflow provenance (S2). S0 (#245) adds
`commons_exportable()`; S1 (#228) adds the Commons owner and the device sphere. S2a needs neither
to be merged: the owner and sphere are attributes of the library, which the web sets.

## Decisions

### Module layout
- `zebra_agent/provenance.py` (no Django): `canonical_content()`, `content_sha256()`,
  `NotHashableError`, `strip_commons()` / `read_commons()`, `Exposure`, `next_block()`
  (the local-change rules), `ANCESTOR_WINDOW = 32`, `LOCAL_TAGS`.
- `WorkflowLibrary.save()` in `library.py` does the I/O. Kept out of S1's `zebra_agent/commons/`
  package to avoid a clash with S0's `commons.py` module.

### Canonical content
`_CanonicalLoader` is a `SafeLoader` subclass whose implicit resolvers omit the timestamp tag.
Strip `commons`, top-level `name`, and `llm-defined` / `system` from `tags` (an empty `tags` is
then dropped, so `tags: []`, no tags and `[llm-defined]` hash the same). Every value must be a
JSON type with string keys and finite floats; otherwise `NotHashableError(reason)`. Then
`json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` → UTF-8 → sha256.

### The block on disk
Appended as the last top-level key. The old block is removed textually (from a column-0
`commons:` line to the next column-0 key), so comments and formatting survive; if the result
does not parse back to the same data the YAML is re-dumped instead. Every key is written, `null`
where unset, in a fixed order.

### save(yaml, *, writer, parent=None, exposure=None, filename=None, llm_defined=False)
1. Strip any `commons` block from the incoming YAML (an LLM can never set it), tag
   `llm-defined` if asked, parse (raises `ValueError` as `add_workflow` did).
2. Parent: the named `parent`, else the active workflow with the same name, if any. Its block
   (if any) and its stripped YAML are read.
3. Leak guard: with an exposure that has texts, `LeakGuard(run_texts, goal_texts, parent_yaml,
   allow_text).check()`. Hits with `exposure.reject` raise `LeakGuardRejected` (nothing written);
   otherwise the save goes ahead (the writer kept them, #237).
4. `next_block(parent_block, parent_hash, new_hash, ...)`:
   - no parent: fresh block, `sphere` = `tainted_by` = [library sphere].
   - same hash as the parent: the parent's block, unchanged.
   - changed: `parent_sha256` = parent hash, `ancestors` = [parent hash] + parent's ancestors,
     capped at 32; `origin_pubkey` = null; `tainted_by` ∪ {library sphere}; `share_with` = [];
     `supervised`, `sphere`, `fork_of`, `adopted_at` inherited.
   - `foreign_users` = parent's OR the exposure holds a user id other than the owner. With no
     owner known, any user id counts (fail closed).
5. Write a new file (`_N.yaml` if taken, never overwrite), clear the cache.

`writer` is a label (`human`, `creator`, `variant_creator`, `optimizer`, `gym`) used in logs.
Taint does not depend on it: every local change marks the sphere (so leak-guard `kept` results
count as tainted).

### Exposure
`Exposure(run_texts, goal_texts, allow_text, user_ids, reject)` with `to_dict()` / `from_dict()`
so the optimizer can hand it to the gym inside `pending_gym`. Sources of user ids:
- creator / variant creator: the goal process's `__user_id__`.
- optimizer: `evaluation.run_exposure_users`, from the analyzer's `run_user_ids` (users of every
  run in the analysis window plus continuation chains).

### Owner and sphere
`WorkflowLibrary(owner_user_id=None, sphere="local")`. The web sets both on init from
`api/commons_owner.py`: `SystemStateModel.commons_owner_user_id` / `sphere` if S1 has added them,
else the first user (lowest id) and `local`. While no owner is known it retries on each
`ensure_initialized()`.

### Readers
`get_workflow_yaml()` returns the YAML without the block (it feeds the evaluator, optimizer,
variant creator and gym). `WorkflowInfo.commons` carries the block for `commons_exportable()`.

## Migration

Existing workflows have no block. They gain one the next time they are saved; their parent hash
is computed from their current content. Built-in installs copy files as before and get a block
on their first save. Definition ids do not change in S2a (the `c:` id is S2b), so metrics,
history and in-flight processes are unaffected. Old files without a block are still loaded,
listed and selected exactly as before.

## Risks

- A writer that sees other users' runs without listing their ids would under-taint. The only
  multi-user exposure today is the dream cycle's metrics analysis, which records them.
- With no owner known the library fails closed: any user id marks `foreign_users`, which never
  clears. The web resolves the owner before the first goal runs.
