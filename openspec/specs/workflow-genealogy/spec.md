# workflow-genealogy Specification

## Purpose
TBD - created by archiving change private-genealogy. Update Purpose after archive.

## Requirements

### Requirement: Local change journal
`WorkflowLibrary.save()` SHALL append one record per saved file to a local journal
(`<library>/.lineage/journal.jsonl`) with the time, file, workflow name, content hash, parent
hash, writer, sphere, device, the reason the writer passed (or null) and the leak-guard status
with each hit's kind, location and source. It SHALL NOT write the hit text, and SHALL NOT change
the `commons` block or the content hash. A journal write failure SHALL NOT fail the save.

#### Scenario: Optimizer save is journaled with its reason
- **WHEN** the optimizer saves a modification whose priority rationale is "three failed runs"
- **THEN** the journal gains a `saved` record with writer `optimizer`, the new hash, the parent
  hash and reason text "three failed runs"

#### Scenario: Save-time rejection is journaled without a file
- **WHEN** a rejecting exposure's leak guard refuses a save
- **THEN** no file is written and the journal gains a `rejected` record with the hit kinds and
  no hit text

### Requirement: Reasons are only ever recorded ones
Writers SHALL pass only a reason they recorded: the evaluator's rationale (optimizer, gym) or the
selector's `voice`, else its reasoning (creator, variant creator). A human save SHALL pass none.
The genealogy page SHALL show "No reason recorded" when there is none.

#### Scenario: Creator uses the selector's voice
- **WHEN** the creator saves a workflow and the process `selection` has a `voice`
- **THEN** the journal reason is that voice with kind `voice`

### Requirement: Lineage DAG of one workflow
`build_genealogy(library, name)` SHALL return the versions linked to the workflow by content hash
(`parent_sha256`, `ancestors`, `fork_of`) over active and retired files, one node per hash, with
edges from parent to child. Ancestor hashes with no file SHALL appear as hash-only nodes.
Each node SHALL carry hash, date, writer, sphere, device, `tainted_by`, `foreign_users`, retired
state and reason, leak-guard record, the change reason and a diff to its parent when both files
are present.

#### Scenario: Two optimizations give three versions
- **WHEN** a workflow is saved by a human and then optimized twice
- **THEN** the genealogy has three nodes in a chain, the two newer with a diff to their parent and
  the optimizer's reasons

#### Scenario: Legacy and built-in versions are labelled
- **WHEN** a file has no `commons` block
- **THEN** its writer is `built-in` if its hash is a shipped built-in's, else `unknown`

### Requirement: Private genealogy page
`GET /workflows/<name>/genealogy/` SHALL render the genealogy server-side as an inline SVG
layered DAG plus a version list, with frame tokens only, the voice colour only for Zebra's
reasons, and no JavaScript. Share status per sphere and forks SHALL show empty states until
S3b-1 provides data. An unknown workflow SHALL return 404.

#### Scenario: Page renders three versions
- **WHEN** the owner opens the genealogy of a workflow optimized twice
- **THEN** the page shows three versions, two diffs, both reasons and the share-status empty state

#### Scenario: Unknown workflow
- **WHEN** the genealogy of a workflow that does not exist is requested
- **THEN** the response is 404

### Requirement: Genealogy and Commons pages require login
With the production middleware stack, an anonymous GET of `/workflows/<name>/genealogy/` or
`/commons/` SHALL redirect to `LOGIN_URL` (with `next`), and an authenticated GET SHALL render the
page. A unit test SHALL check this against the `MIDDLEWARE` declared in `settings.py`, so removing
`LoginRequiredMiddleware` or exempting either view fails CI.

#### Scenario: Anonymous visitor is redirected
- **WHEN** an anonymous visitor requests `/workflows/Old%20Search/genealogy/` or `/commons/`
- **THEN** the response is a 302 to `/auth/login/?next=<path>`

#### Scenario: Logged-in owner sees the page
- **WHEN** a logged-in user requests the same pages
- **THEN** each response is 200

#### Scenario: Guard removed
- **WHEN** the genealogy view is marked `login_not_required` or `LoginRequiredMiddleware` is removed from `settings.MIDDLEWARE`
- **THEN** the test fails
