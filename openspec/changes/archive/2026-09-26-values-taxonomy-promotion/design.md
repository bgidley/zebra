## Context

`ValuesTagModel` (`zebra_values_tags`) already has `status`, `usage_count` and `promoted_at`. Curation is done by the maintainer or owner on this table, which only exists on the Django side. Task actions never curate. They only read the approved set and record confirmations through `ProfileStore`.

## Decisions

- **Curation lives in a Django-side module, not in the `ProfileStore` ABC.** Only the web app and the management command need it. Widening the agent-facing interface would add surface with no caller. The module uses sync ORM functions, and the async view wraps them with `sync_to_async`.
- **Reject keeps the row, as `rejected`.** Deleting it would let the next confirmation recreate it as a fresh candidate, losing the curator's decision. Rejected rows still count usage, so a tag that keeps coming back stays visible.
- **Merge is a redirect, not a delete.**
  - The source must be `candidate`, `promoted` or `rejected`.
  - The target must be in the same field and be `seeded`, `promoted` or `candidate`.
  - Usage moves to the target. The source becomes `merged` with `merged_into=<target slug>` and `usage_count=0`.
  - Tags already merged into the source are repointed to the target, so chains never form.
  - `record_confirmed_tags` sends later increments for the source slug to the target.
- **Allowed transitions:**
  - promote: `candidate|rejected → promoted` (sets `promoted_at`)
  - reject: `candidate|promoted → rejected`
  - demote: `promoted → candidate` (clears `promoted_at`)
  - `seeded` and `merged` rows are never the subject of an operation. Anything else raises `TaxonomyError`.
- **Suggestions are advisory.** `VALUES_TAG_PROMOTION_THRESHOLD` in `ZEBRA_AGENT_SETTINGS` (env `ZEBRA_VALUES_TAG_PROMOTION_THRESHOLD`, default 3) marks candidates as "suggested" on the page and for `list --suggested`.
- **Prune** deletes only `candidate` rows with `usage_count <= max_usage` (default 1) that are older than `days` (default 90). Candidates start at usage 1, so a `usage_count == 0` rule would never match anything.

## Risks / Open questions

- Old profile versions keep merged or rejected slugs. The ethics prompt shows them unchanged, which is acceptable because the free-text fields still carry the meaning.
- The curator page is open to any authenticated user. That matches the single-user identity model (F4). Revisit it for multi-user (F59).
