## Context

S2a shipped `zebra_agent/provenance.py` (canonical hash, `commons` block, local-change rules) and
`WorkflowLibrary.save()`. S1 shipped the Zebra/device keys, `DEVICE_CERT` / `DEVICE_REVOKE` and
`verify_attributed()`. The design is `specs/zebra-commons-design.md` § Workflow provenance and
§ Task actions. Nothing here touches the network.

## Goals / Non-Goals

**Goals:** content-hash definition ids; a signed single-workflow export file and its
verification; `save(writer="adopt")`; the owner-governed `sharing` trust domain; `commons_pii_scan`.

**Non-Goals:** the judged import workflow (`commons_import.yaml`, gym import mode, supervised
pre-run approval: S3 #230); `commons_offer.yaml`, publishing, relays (S4/#246); sync and `SKILL`
(S3b); a web UI for export/import (management commands only).

## Decisions

### Definition id
`zebra.definitions.loader` stays Commons-agnostic but reads `commons.content_sha256` when it is a
non-empty string: `id = "c:" + sha256(f"{content_sha256}:{name}")[:16]`. The block is trusted
because only `WorkflowLibrary.save()` writes it. Migration: a workflow moves to the `c:` id on its
next save (S2a stamps every save). Old ids stay in the definition store, so processes created
from them resume from their stored definition; metrics and memory key on the workflow name.

### Export file
```json
{"format": "zebra-workflow-export", "version": 1,
 "event": {NIP-01 event, kind 31229 (provisional), signed by the device key,
           tags [["x", sha256], ["zebra", zebra_pubkey], ["t","zebra-commons"], ["v","1"]],
           content = JSON {"name", "yaml", "commons"}},
 "chain": [DEVICE_CERT events for the signing device]}
```
- The YAML is the library YAML with the block and local tags (`llm-defined`, `system`) removed;
  neither is hashed, so the hash is unchanged.
- Verification (`verify_export`): well-formed JSON → event signature → attribution
  (`verify_attributed` against the declared Zebra pubkey, chain from the file plus any revokes the
  verifier holds; `expected_zebra` pins a publisher) → `x` tag == block hash == recomputed hash of
  the YAML → block `foreign_users` is exactly `false`. Any failure gives `ok=False` and a reason;
  one changed byte anywhere fails at one of these steps (JSON, id/signature, or chain).
- Export refuses unless `commons_exportable()` and the device is certified; it self-verifies
  before returning.
- Web glue (`zebra_agent_web/api/commons_export.py`) loads the device secret and the cert chain
  from S1's tables; the device needs a `DEVICE_CERT` (the Zebra-key device self-certifies in S1).

### Adoption
`save(yaml, writer="adopt", received=block, expected_sha256=hash, name=display_name,
origin_pubkey=publisher)`:
- hash of the YAML (block stripped) must equal `received.content_sha256` and `expected_sha256`;
- `received.foreign_users` must be `false` (never adopt something its publisher must not share);
- the received YAML's local tags are dropped, the name is replaced, the hash is re-checked;
- the block is copied verbatim except `sphere` (this library's), `share_with: []`,
  `adopted_at` (now), `supervised: true`, `origin_pubkey` (kept, else the publisher);
- no exposure, no leak guard, no `llm-defined`;
- a name already taken by an active workflow is refused (`ValueError`) unless it already holds
  the same hash (idempotent re-adopt returns that file). This avoids a `_N` copy that would
  shadow the local workflow.

### Sharing domain
`"sharing"` joins `DEFAULT_DOMAINS`. The trust gate keeps one code path; for domains in
`OWNER_GOVERNED_DOMAINS = {"sharing"}` the user whose level (and freed status) is read is the
Commons owner from `__workflow_library__.refresh_owner()`. No library or no owner → SUPERVISED
(approve). Emergency override and the kill switch already cover every domain.

### Personal-data scan
`zebra_tasks/commons/pii_scan.py`, action `commons_pii_scan`. Inputs: `yaml`, `golden_tasks`
(list of strings or dicts), `model` (default `low`), `output_key`. It walks every string of the
parsed workflow except the `commons` block (prompts, defaults, examples, descriptions) and of the
golden tasks. Rules first (reserved example domains such as `example.com` and `{{templates}}` are
not findings); then a low-tier `complete_json` call over the same texts. `clean` only when the
rules find nothing and the LLM answers `personal_data: false`. Any parse error, missing LLM or
bad reply → `rejected` with `failed_closed: true`. Hint `always_reversible`: it reads and makes one
LLM call (the same convention as the trust and ethics gates, #245).

## Risks / Trade-offs

- Revocation without relays: a verifier only knows the revokes it holds; a file signed by a
  device revoked elsewhere still verifies until S3b-2 brings receipts. Documented.
- Rule false positives (a phone-like number in a prompt) reject a share; that is the safe side.
- Adopted workflows are flagged `supervised` but supervision is enforced only from S3 (#230).
  `commons_import --adopt` is a human action at the command line, equivalent to adding a YAML by
  hand.
