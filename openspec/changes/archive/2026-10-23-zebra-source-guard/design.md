## Context

`zebra_source` (`zebra-tasks/zebra_tasks/agent/zebra_source.py`) already sandboxes reads to
allowlisted top-level entries, refuses dot-entries, databases, keys, `tmp/` and symlinks, and on a
miss suggests up to 5 nearest paths (#190, #211). This change makes a clear miss read the right
file directly and makes refusals explain themselves.

## Decisions

**Confident match.** `confident_match(root, rel)` collects readable files (the same `_source_files`
walk that suggestions use, so it can only pick files a read allows). If any file has the requested
name: exactly one → that file; several → none. If no file has that name: `difflib` close matches
with cutoff 0.9 whose file name is also ≥ 0.85 similar; exactly one → that file. Name-first
mirrors the suggestion order and catches the commonest error (right file, wrong directory). The
name check matters: a long shared directory alone lifts `…/agent/thx.py` vs `…/agent/thing.py` to
0.93, while the names score 0.71. A one-letter typo (`stuk.py`, `selecter.py`) still matches.

**Same run.** `_read` handles the miss by reading the match and prefixing
`Note: '<requested>' does not exist; read '<actual>' instead (the only close match).` The note is
part of `text`, so an agent sees it in its tool result, and `output.path` records the real file for
callers that check.

**Unknown top level.** `resolve_source_path` now separates three cases: outside the root
(refuse), a sensitive part (dot-entry, `DENIED_PARTS`, `DENIED_SUFFIXES`; refuse), and a
non-allowlisted top level. The last is refused only if that top-level entry exists; otherwise the
returned path does not exist, so the caller treats it as a miss. Nothing outside the allowlist is
ever opened: the miss path reads only `confident_match` results.

**Messages.** `missing_path_message` keeps the "not deployed" wording for an allowlisted entry
that is absent, and now also adds suggestions in that case.

## Risks

- A confident match could be the wrong file. The note names both paths, and the agent can still
  read another one. The outcome review reads by path and will see the note.
