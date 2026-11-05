## Context

Design source: `specs/zebra-commons-design.md` § "Skill sync between own devices (S3b)" and
"Worked what-ifs". GitLab #236 (S3b-1). Transport, encryption and receipts are #246 (S3b-2), so
this change runs over an in-memory relay only and nothing in production publishes yet.

## Goals / Non-Goals

**Goals:** the decisions (what may be proposed, who must approve, what may be sent, what a receiver
accepts, how versions merge) with real tests, including the two-device E2E scenarios of #236.

**Non-Goals:** the `nostr-sdk` client, the private strfry relay, NIP-44 encryption, relay receipts,
an offline queue, building the sync service from the web settings (all #246); a "Share" button on
the workflow page (needs that service; the manual path exists as `start_share(manual=True)`).

## Decisions

1. **Where the logic lives.** Pure parts in `zebra_agent/commons/` (`client.py`, `skill.py`,
   `sync.py`: merge decision, share status, candidates, `SyncService`). Decisions that need a human
   are system workflows (`skill_share.yaml`, `skill_receive.yaml`) so the approvals are ordinary
   human tasks with the usual UI, journal and cost accounting. Their steps are task actions in
   `zebra_tasks/commons/` (`sync_actions.py`, `confidentiality.py`, `sensitivity.py`) that read the
   `SyncService` from `context.extras["__commons_sync__"]` and fail closed without it.
2. **Encryption placeholder.** S3b-1 events are plaintext with an `["enc","none"]` tag but are
   addressed (`p`) to one recipient device each; only recipients in `share_with` spheres get one.
   #246 replaces the content with NIP-44 ciphertext without changing who gets a copy.
3. **Same Zebra only.** A receiver accepts a `SKILL` only from a device certified by its own Zebra
   key (cert chain from the event content plus the certs and revokes the receiver holds). The
   sender's sphere comes from its cert, never from the event body.
4. **Share decisions are journal records** (`event: "share"` in the #238 lineage journal) keyed on
   (content hash, sphere) with status `proposed`, `approved`, `declined`, `sensitive`, `blocked`,
   `sent`, `received`, plus `skipped` / `failed` (not decisions: Zebra may ask again).
   `skill_share_prepare` writes `proposed` only when it routes `propose`, so a skipped or failed
   process never shows as "waiting for approval". Candidates skip any (hash, sphere) already
   decided, so Zebra never nags,
   and a new hash (every content change resets `share_with`) is a new decision. Approval writes
   the sphere into `share_with` in place (mtime kept) only if the current hash is still the
   approved one.
5. **Approval routing** (`skill_share_route`):
   - sensitive and target observed: `never` unless manual; manual goes to `observed`.
   - target observed, or `tainted_by` holds an observed sphere: `observed` →
     `observed_share_approval` (needs `visible_on_managed_device: true` when the target is observed).
   - sensitive (not observed): `ask` → `share_approval` (no autonomy skip).
   - otherwise `trusted` → `trust_gate (sharing)` → `proceed` records approval, `approve` →
     `share_approval`.
6. **Triggers.** `SyncService.after_run(library, metrics, name)` proposes one workflow once it has
   `MIN_RUNS_TO_SHARE` successful runs; `after_dream(...)` proposes every eligible workflow (the
   dream cycle resets `share_with` when it rewrites one). `assess_and_record` calls `after_run`
   after recording a successful goal run and `AgentLoop.run_dream_cycle` calls `after_dream`,
   both only when a service is in the engine extras. `SyncService.direction` defaults to
   `ZEBRA_SYNC_DIRECTION` (`both`; unknown → `off`). `receive_pending()` starts one *Skill
   Receive* per new event addressed to this device.
7. **Lineage merge.** `merge_decision(local_block, incoming_block)`: `new`, `noop`, `fast_forward`
   (local hash in incoming ancestors), `stale` (incoming hash in local ancestors), `fork`.
   Fast-forward adopts with `replace=True` (the old file is retired, superseded by the same name).
   A fork adopts as `<name> (from <sphere>)` with `fork_of` = local hash, and the local block gets
   `fork_of` = incoming hash; `resolve_fork(keep=mine|theirs|both)` clears it.
8. **Lineage-aware lookup.** `_files_named` (newest first) moves to the front the newest file that
   is not an ancestor of another same-name file, preferring files without `fork_of`; the curator
   retires an older copy only when its hash is in the current copy's lineage (or either has no
   block, the old behaviour) and skips any file with `fork_of`.

## Risks / Trade-offs

- Plaintext events until #246: acceptable because nothing publishes outside tests.
- Confidentiality rules are heuristic (the design says "not proof"); URLs other than reserved
  example domains block, which will catch some harmless public links: fail closed by choice.
- Share decisions live in the journal, a local file. Losing it means Zebra may ask again, and
  (leak taint fails closed) that versions with no `saved` record are never shared until rewritten.
