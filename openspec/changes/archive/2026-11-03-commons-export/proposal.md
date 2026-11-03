## Why

S2a (#229, `commons-provenance`) gave every workflow a canonical hash and a library-owned
`commons` block. The Zebra Commons (#41) still cannot move a workflow between Zebras: there is no
signed file to carry one, nothing to check it on arrival, no way to put a received workflow into
the library without it looking like a local rewrite, no personal-data check before anything
leaves, and no trust domain that governs sharing. S3 (judged import, #230) and S3b-1 (sync, #236)
both build on these pieces, so they land first. This is S2b of #229. Refs #229.

## What Changes

- **Content-addressed definition ids:** the loader derives the id from the block when present:
  `c:` + sha256(`content_sha256` + `:` + `name`)[:16]. An adopted "Web Research" no longer
  collides with the local one. Files without a block keep `sha256(name:version)`; old definitions
  stay in the store, so in-flight processes resume; metrics key on the name, so history is kept.
- **Signed single-workflow export file** (`zebra_agent/commons/export.py`): a JSON document
  holding one Nostr-style event signed with this deployment's S1 **device key**, carrying the YAML
  (block and local tags removed), the `commons` block and the hash (`x` tag), plus the
  `DEVICE_CERT` chain that attributes it to the Zebra. `verify_export()` checks the signature,
  the cert chain, that the hash recomputes from the YAML and that the block is not
  `foreign_users`. Export is refused unless `commons_exportable()`. `manage.py commons_export` /
  `commons_import` (verify; `--adopt` to adopt) drive it.
- **`sharing` trust domain** (REQ-NET-006) in the trust taxonomy. It is **owner-governed**: the
  trust gate reads the level of the Commons owner (#228 `commons_owner_user_id`, via the library),
  not of the process user, and fails closed to SUPERVISED when no owner is known.
- **`commons_pii_scan` task action** (`zebra-tasks`): rule-based (emails, phone numbers, card
  numbers, UK NI numbers, postcodes, IPs, secrets/tokens, URLs with credentials) plus a low-tier
  LLM scan of every string in the workflow (prompts, defaults, examples) and of golden tasks.
  Routes `clean` / `rejected`; fails closed on any error. `reversibility_hint: always_reversible`
  (reads plus one LLM call, no lasting effect).
- **`WorkflowLibrary.save(writer="adopt")`**: keeps a received block verbatim after checking the
  YAML's hash equals the block's and the offered/sent hash. Only the local `name`, `sphere`,
  `share_with: []` and adoption bookkeeping (`adopted_at`, `supervised: true`, `origin_pubkey`
  when absent) change; local tags are dropped and `llm-defined` is never added; a taken name is
  refused rather than shadowed.

## Capabilities

### New Capabilities
- `commons-export`: content-hash definition ids, the signed export file and its verification,
  the owner-governed `sharing` trust domain, the personal-data scan and adoption.

### Modified Capabilities
<!-- None: commons-provenance gains a writer but its requirements are unchanged -->

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A stamped workflow loads with a `c:` definition id derived from its hash and name, so an adopted workflow with the same name and version as a local one never shares its id; unstamped files keep their old id and still load and run | Unit tests in `zebra-py` (loader) and `zebra-agent` (two same-name/version workflows with different content get different ids; a legacy file keeps `sha256(name:version)`) |
| O2 | An exportable workflow exports to a signed file that verifies, attributed to this Zebra through its `DEVICE_CERT`; changing any one byte of the file, a revoked or uncertified device key, a hash mismatch or `foreign_users` makes verification fail; a non-exportable workflow (system, `foreign_users`, no block) is refused | `zebra-agent/tests/test_commons_export.py` (byte-flip loop over the file), `zebra-agent-web` command tests |
| O3 | Adopting a verified export keeps `content_sha256` and lineage verbatim, sets `supervised: true`, `share_with: []`, `adopted_at`, never adds the `llm-defined` tag, gets a distinct definition id, and refuses a hash mismatch or a taken name | E2E test: export → verify → adopt in a second library; unit tests of the refusals |
| O4 | `sharing` is a trust domain shown with the others; a trust gate on `sharing` follows the owner's level, not the process user's, and fails closed (approve) with no owner | `zebra-tasks` trust-gate tests; web trust page lists `sharing` |
| O5 | `commons_pii_scan` routes `rejected` for personal data in prompts, defaults, examples or golden tasks (rules or LLM), `clean` only when both pass, and `rejected` when the LLM is unavailable or unparseable | `zebra-tasks/tests/test_commons_pii_scan.py` |
