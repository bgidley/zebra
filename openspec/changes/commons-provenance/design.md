## Context

Design: `specs/zebra-commons-design.md` § Workflow provenance (S2). S0 (#245) adds
`commons_exportable()`; S1 (#228) adds the Commons owner and the device sphere. S2a needs neither
to be merged: the owner and sphere are attributes of the library, which the web sets. The
branch merges S0's branch (`f245/commons-safety`) as its base for `commons_exportable()`.

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
   - same hash as the parent: the parent's block, unchanged (except that `foreign_users` still
     takes this writer's exposure into account).
   - changed: `parent_sha256` = parent hash, `ancestors` = [parent hash] + parent's ancestors,
     capped at 32; `origin_pubkey` = null; `tainted_by` ∪ {library sphere}; `share_with` = [];
     `supervised`, `sphere`, `fork_of`, `adopted_at` inherited.
   - `foreign_users` = parent's OR the exposure holds a user id other than the owner OR the
     exposure's `foreign_users` (taint folded in from shown workflows, below). With no owner
     known, any user id counts (fail closed). The exposure's `tainted_by` joins the block's.
   - **Shown workflows**: a writer shown other workflows can paraphrase their content into a new
     lineage that has no parent, so the parent rule alone would launder their taint. The
     optimizer's exposure (`optimizer_exposure`) therefore folds in the `commons` blocks
     (`WorkflowLibrary.commons_block(name)`) of every workflow in `existing_workflows` (whose
     YAML its create prompt includes) and the evaluator's `definitions_shown` (whose judgement
     drives the priorities and rationale it acts on) via `Exposure.with_shown()`: OR in
     `foreign_users`, add their `tainted_by`. An unreadable block counts as foreign. The goal-time
     creator shows only names and descriptions of up to 5 workflows, not their YAML, and is not
     folded (see risks).
5. Write a new file (`_N.yaml` if taken, never overwrite), clear the cache.

A save-time `LeakGuardRejected` is a failed change in the optimizer (`failed_changes`, nothing
written) and a rejected candidate in the gym.

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
`WorkflowLibrary(..., owner_user_id=None, sphere="local", owner_resolver=None)`. The web passes
`api/commons_owner.py:resolve_commons_owner` as the async resolver: S1's
`SystemStateModel.commons_owner_user_id` / `sphere` when those fields exist, else the routine
owner (`resolve_routine_user(None)`: first active superuser, else the first active user) and
`local`. `await library.refresh_owner()` runs while the owner is unknown, from
`agent_engine.ensure_initialized()` and every daemon tick, so a fresh install picks the owner up
once setup has created the first user.

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
- The goal-time creator's prompt lists names and descriptions of existing workflows (no YAML); their taint is not folded in. A description is short and LLM-written from the workflow, so the risk is low; revisit if the creator ever shows definitions.
