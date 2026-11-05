## Why

One Zebra runs on several devices (home, work), and skills learnt in one place should be usable in
the other, while data never crosses and nothing reaches an observed (employer-managed) device
without a human saying so. S1 (#228) gave devices keys, spheres and `observed`; S2a/S2b (#229)
gave workflows a library-owned `commons` block (`sphere`, `tainted_by`, `share_with`,
`foreign_users`, `ancestors`, `fork_of`), adoption and the personal-data scan. This change (S3b-1,
GitLab #236, epic #41) adds the sync **logic** over an in-memory transport; the real Nostr relay,
NIP-44 encryption and receipts are #246.

## What Changes

- **`CommonsClient` ABC** (`publish`, `subscribe`, `fetch`) and an `InMemoryCommonsClient` over a
  shared `InMemoryRelay` (`zebra_agent/commons/client.py`). The hard filter refuses a `SKILL` event
  on any relay that is not private.
- **`SKILL` events** (`zebra_agent/commons/skill.py`, provisional kind 4236): built only for the
  certified, unrevoked devices of the spheres in the workflow's `share_with` (one event per
  device, `p`-tagged); content is the relabelled YAML, the `commons` block, a stats snapshot, the
  sending device and its cert. `verify_skill` checks addressee, signature, cert chain to this
  device's own Zebra, the hash (YAML = block = `x` tag), `foreign_users: false` and that the
  receiver's sphere is in the sent `share_with`.
- **Suggest-and-approve sharing** (system workflow *Skill Share*): Zebra proposes a workflow to
  another sphere after `MIN_RUNS_TO_SHARE` (2) successful runs, or after the dream cycle. Gates, all
  failing closed: `commons_exportable`, leak-guard status (`kept` = tainted, not proposed),
  `commons_pii_scan`, the new `commons_confidentiality_scan` (internal hosts, codenames, customer
  names, credentials, URLs, `SYNC_CONFIDENTIAL_PATTERNS`, plus a low-tier LLM) and the new
  `commons_sensitivity_check` (low-tier LLM). A sensitive workflow is never proposed to an observed
  sphere; a manual share there needs a "visible on a managed device" confirmation.
  Observed-sphere approvals (target observed, or `tainted_by` holds an observed sphere) are the
  dedicated `observed_share_approval` human task, never `trust_gate`, so freeing Zebra cannot skip
  them. Otherwise `trust_gate (sharing)` may let earned autonomy skip the "Share X with
  <sphere>?" task. Every task shows the workflow, the diff against the copy last shared with that
  sphere and Zebra's reason.
- **Send** (`skill_send`): only when `SYNC_DIRECTION` allows sending, the current hash is the
  approved one and both scans passed again on the exact bytes sent.
- **Receive** (system workflow *Skill Receive*): `SYNC_DIRECTION` allows receiving, the event
  verifies, the definition validates and uses only registered actions, both scans re-run, then
  `trust_gate (sharing)` (or a human approval), then adoption through `save(writer="adopt")`.
- **Lineage merge** on `commons.ancestors`: same hash no-op; incoming descends from local
  fast-forward (the old file is retired); local descends from incoming ignored (stale); otherwise a
  fork saved as `<name> (from <sphere>)` with `fork_of` on both copies and a choice human task
  (keep mine / keep theirs / keep both).
- **Library and curator resolve by lineage:** the newest-file lookup prefers a descendant over its
  ancestors and a non-fork over a fork; the curator's `SUPERSEDED_COPY` retires only ancestors of the
  current copy and never a fork.
- **Genealogy** (#238) shows per-sphere share status (shared, waiting, never proposed, blocked,
  declined) from the lineage journal, and forks awaiting a choice.
- Stats travel as a snapshot in the event and are never merged into the local `MetricsStore`.

## Capabilities

### New Capabilities
- `commons-skill-sync`: the client, `SKILL` events, sharing gates and approvals, send and receive,
  lineage merge and forks, lineage-aware lookup and curation.

### Modified Capabilities
<!-- workflow-genealogy gains share status and forks; its requirements already allowed for them -->

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | No `SKILL` event exists for a workflow until its share is approved (by a human, or by earned `sharing` autonomy where O3 allows it), and then events go only to the certified, unrevoked devices of the approved sphere of the same Zebra; a receiver rejects events from another Zebra, a revoked device or a tampered YAML; a device with `SYNC_DIRECTION` `receive` or `off` never sends | E2E (in-memory relay, home + observed work): zero events before approval, one addressed only to the work device after; `verify_skill` unit tests for wrong Zebra, revoked, hash mismatch; receive-only device publishes nothing |
| O2 | These cases send zero payloads and leave a journal record (`sensitive` / `blocked`): a job-application workflow considered for the observed work sphere, a workflow with a work codename (`SYNC_CONFIDENTIAL_PATTERNS`), a version with a leak-guard `kept` or `error` result on it or any ancestor (including a save-time `kept` under a writer's own record), a version or non-built-in ancestor with no journal `saved` record, a workflow learnt from a second user's runs (never proposed at all); the confidentiality and sensitivity checks fail closed when their LLM is unavailable, errors or replies malformed JSON | E2E scenarios plus unit tests of `commons_confidentiality_scan` / `commons_sensitivity_check` |
| O3 | Approvals for an observed sphere (target observed, or `tainted_by` holds an observed sphere) are an `observed_share_approval` human task that a freed owner or an AUTONOMOUS `sharing` level does not skip; only an unobserved target with an untainted workflow lets an earned `sharing` level skip the "Share X with <sphere>?" task; an approval is void once the content changes | Workflow tests with a freed owner, AUTONOMOUS sharing (on the sender, for an unobserved target with observed `tainted_by`) and an edit after the proposal voiding its approval |
| O4 | A workflow approved at work appears in the home library with the same content hash after the receiver re-verifies, re-scans and passes `trust_gate (sharing)`; receiving the same hash again is a no-op and an older ancestor is ignored; edits on both sides leave both versions with `fork_of` set and a choice task, and neither the library lookup nor the curator retires either fork | E2E scenarios; merge, library and curator unit tests |
| O5 | The private genealogy page (#238) shows the workflow's per-sphere share status and any fork waiting for a choice | `zebra-agent` genealogy tests and the web genealogy view test |
