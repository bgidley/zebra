## Why

F18 (#18) persists every user-confirmed values tag as a `candidate`, but nothing ever promotes one. `extract_values_tags` only anchors the LLM on `seeded + promoted`, so the taxonomy never learns and the candidate table grows forever. Closes #106.

## What Changes

- The tag lifecycle grows from three states to five: `seeded`, `candidate`, `promoted`, `rejected`, `merged`. A new nullable `merged_into` column points a merged tag at its surviving slug.
- Curator operations **promote**, **reject**, **demote** and **merge** live in one shared module, `zebra_agent_web/values_taxonomy.py`.
- Candidates whose `usage_count` is at or above `VALUES_TAG_PROMOTION_THRESHOLD` (default 3) are flagged as suggestions for promotion. Nothing is promoted automatically.
- A new `manage.py values_taxonomy {list,promote,reject,demote,merge,prune}` command. `prune` deletes stale single-use candidates (`--days`, `--max-usage`, `--dry-run`).
- A `/profile/taxonomy/` curator page for the logged-in user, linked from the nav.
- In both the Django and in-memory stores, `record_confirmed_tags` sends a confirmation of a `merged` slug to its target.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `values-taxonomy`: the lifecycle adds `rejected`/`merged`, and new requirements cover curation, suggestions, pruning and merge redirection.

## Non-goals

- Promotion without a human decision.
- Rewriting slugs inside existing `ValuesProfileVersion` rows. Versions stay immutable.
- Telling the extraction LLM about rejected slugs.
- Curating `seeded` tags. They are first-class by definition and can only be a merge target.

## Impact

- `zebra-agent-web`: model, migration, `values_taxonomy.py`, management command, views, URLs, template, nav, `profile_store.py`, settings.
- `zebra-agent`: `InMemoryProfileStore.record_confirmed_tags` handles merge redirection, and the `ProfileStore` docstring is updated.
- Docs: `specs/zebra-as-is.md`.
