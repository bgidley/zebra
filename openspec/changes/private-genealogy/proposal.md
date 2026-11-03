## Why

S2a (#229) gave every workflow file a `commons` block with its content hash and lineage, but
nothing shows it, and the library forgets who wrote each version and why: `save()` only logs its
writer. The owner cannot see where a skill came from, how it changed or why. #238 (Zebra Commons,
epic #41, design `specs/zebra-commons-design.md` § Genealogy view) asks for a private family tree
per workflow on this deployment. Refs #238.

## What Changes

- **Change journal:** `WorkflowLibrary.save()` appends one record per save (and per save-time
  leak-guard rejection) to a local journal next to the library (`.lineage/journal.jsonl`):
  file, hash, parent hash, writer, time, sphere, device, the reason it was given, and the leak-guard
  status with hit kinds and locations (never the hit text). Local only: never in the `commons`
  block, never exported.
- **Writers pass their reason:** the optimizer and the gym pass the evaluator's rationale and the
  change's leak-guard record; the creator and the variant creator pass the selector's recorded
  `voice` (else its reasoning, labelled as such). A writer with no recorded reason passes none;
  the page says "No reason recorded" and never invents one.
- **Genealogy model** (`zebra_agent/genealogy.py`, no Django): the lineage of one workflow as a DAG
  over content hashes, from `commons.ancestors`, `parent_sha256` and `fork_of`, over active and
  retired files plus the journal. Per version: hash, date, device, sphere, writer (creator /
  variant / optimizer / human / adopted / synced / built-in / unknown), files, retired state and
  reason, `tainted_by`, `foreign_users`, leak-guard record, reason. Ancestors with no file on this
  device appear as hash-only nodes.
- **Page `/workflows/<name>/genealogy/`:** server-rendered template with an inline SVG layered DAG
  (no JS), a version list with a diff to the parent and the reason in the voice style, empty
  states for per-sphere share status and forks (they arrive with S3b-1, #236). Linked from the
  workflow page. Never published.

## Capabilities

### New Capabilities
- `workflow-genealogy`: the local change journal and the private genealogy page.

### Modified Capabilities
<!-- None: commons-provenance's block is unchanged. -->

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Every save records who wrote the version, when, on which sphere and device, and why (only a reason a writer actually recorded), plus leak-guard status, without the hit text and without touching the `commons` block | Unit tests: optimizer, gym, creator, variant creator and human saves each append a journal record with the right writer and reason; a save-time leak rejection records `rejected` with no file; the block and hash are unchanged by the journal; a hit's text is not in the journal |
| O2 | `/workflows/<name>/genealogy/` shows the lineage as a DAG: optimizing a workflow twice gives three versions linked parent to child, each with hash, date, writer, sphere and a diff to its parent with the optimizer's reason | Unit test of `build_genealogy` and a Django view test rendering three versions, two diffs and both reasons; prod: the page renders for a real workflow |
| O3 | What the data does not hold yet is shown honestly: legacy (blockless) files, built-ins, retired versions and ancestors known only by hash are labelled; share status per sphere and forks show clear empty states; no reason is invented | Unit tests for legacy, built-in, retired and hash-only nodes and for the empty states and "No reason recorded" |
| O4 | The page follows the web UI rules: frame tokens only, voice colour only for Zebra's reasons, light and dark, WCAG AA, usable on a phone, no new JS | `test_theme.py` passes on the new templates; Playwright container screenshots at phone and desktop widths in light and dark with no horizontal page scroll |
