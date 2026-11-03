## Context

Design: `specs/zebra-commons-design.md` § Genealogy view. S2a (#229, shipped) gives each file a
`commons` block (`content_sha256`, `parent_sha256`, `ancestors`, `fork_of`, `sphere`,
`tainted_by`, `share_with`, `foreign_users`). `save()` takes a `writer` but only logs it, and the
reasons for a change live only in dream-cycle process properties. S3b-1 (#236, sync and share
status) is not built: `share_with` is always `[]` and `fork_of` always null.

## Decisions

### A local journal, not the block
Writer, time, reason and leak-guard detail are local facts. Putting them in the `commons` block
would ship them with an export (S2b) and a reason may quote run specifics. So `save()` appends to
`<library>/.lineage/journal.jsonl` (one JSON object per line, append-only, `_append` swallows
`OSError` with a warning: a journal failure never blocks a save). Record:

```
{"v": 1, "at": ISO-8601 UTC, "event": "saved" | "rejected", "name", "file" (null when rejected),
 "writer", "content_sha256", "parent_sha256", "parent_name", "sphere", "device",
 "reason": {"text", "kind": "voice" | "reasoning", "source"} | null,
 "leak_guard": {"status", "hits": [{"kind", "where", "source"}]} | null}
```

- Hit **text is dropped** before writing: the journal must not hold run specifics the workflow
  was refused for.
- `save(..., reason=None, leak=None)`: `reason` is a string (kind `reasoning`) or a dict
  `{text, kind, source}`; `leak` is the writer's `leak_record()`. Save-time kept hits are merged
  into the record (`kept`); a save-time `LeakGuardRejected` writes a `rejected` record then
  re-raises.
- `device`: a new `WorkflowLibrary.device` attribute (default None). The web fills it from
  `SystemStateModel.device_label` in `resolve_commons_owner` (now returning
  `(owner, sphere, device)`; a 2-tuple still works).

### Where reasons come from (never invented)
| Writer | `writer` | Reason |
|---|---|---|
| Optimizer (create / ungated modify) | `optimizer` | priority `rationale`, kind `reasoning`, source `evaluator` |
| Gym promotion | `gym` | candidate `reason` (same rationale) + the change's `leak_guard` |
| Creator / variant creator | `creator` / `variant_creator` | process `selection.voice` (kind `voice`, source `selector`), else `selection.reasoning` (kind `reasoning`) |
| Web create, CLI | `human` | none |

### Genealogy model (`zebra_agent/genealogy.py`)
`build_genealogy(library, name) -> Genealogy` (pure over the library's files and journal):
1. Read every active and retired file (retired: strip the retirement marker, keep its meta).
   Hash each (block's `content_sha256`, else computed; unhashable → `file:<stem>` key).
2. Seed with the files named *name*; grow to a fixed point by hash: a file joins when its hash
   is a seed's ancestor / parent / `fork_of`, or its parent / ancestors contain a member's hash.
   This picks up variants under other names.
3. One node per hash (several files can share one; newest wins for display). Edges
   `parent_sha256 → hash`, plus `ancestors[i+1] → ancestors[i]` for links no file states.
   Ancestor hashes with no file become **hash-only** nodes.
4. Writer, reason, device and date: the first journal `saved` record for that hash (the save that
   made the content; by file for an unhashable one), else
   `builtin` (hash in `builtin_hashes()`), else `unknown`. Display labels: `creator`, `variant`
   (variant_creator), `optimizer` (optimizer, gym), `human`, `adopted` (adopt), `synced` (sync),
   `built-in`, `unknown`.
5. Diff: `difflib.unified_diff` of the parent's and the node's stripped YAML (bounded to 400
   lines), only when both files exist here.
6. Layers: longest path from a root (Kahn order); within a layer, by date. A revert to earlier
   content makes a cycle by hash; it is broken at its oldest node and drawn as a dashed side edge.

### Page
`GET /workflows/<name>/genealogy/` (`web_views.workflow_genealogy`) → `pages/workflow_genealogy.html`.
`api/genealogy_view.py` does the layout: a fixed grid (column = layer, row = order in layer),
oldest at the top, the SVG shrinks to the width (`max-width: 100%`), nodes are links to `#v-<hash12>` anchors, `<title>` per node, the
SVG has `role="img"` and an `aria-label`. Colours via CSS variables (frame tokens); the current
version gets `ok`, retired `faint`, hash-only dashed. The version list is the primary content
(newest first): cards with mono hash, date, writer pill, sphere / device, `tainted_by`,
`foreign_users`, retired reason, leak-guard status and hit kinds, the reason as a voice thought
(`components/thought.html` style, `text-voice`) or "Recorded reasoning" label, and a `<details>`
diff (`overflow-x: auto` inside, so the page never scrolls sideways). Empty states: "Share
status per sphere arrives with skill sync (#236)" and "No forks waiting".

## Risks / open questions
- Versions saved before this deploy have no journal record: writer comes from the built-in hash
  or shows "unknown", date falls back to the file's mtime (labelled "file date").
- The journal grows without bound; one line per save, so years of dream cycles are a few MB.
  Compaction can come later.
- A reason may contain run specifics; it stays on this deployment and the page is not published.
- Hash-only ancestors whose files were deleted cannot show a diff.
