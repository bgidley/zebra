> Branch: `f106/values-taxonomy-promotion`. Reference `#106` in commits.

## 1. Data model

- [x] 1.1 `ValuesTagModel`: add the `rejected`/`merged` statuses and a nullable `merged_into` field, plus a migration
- [x] 1.2 `record_confirmed_tags` in `DjangoProfileStore` and `InMemoryProfileStore`: redirect merged slugs to their target

## 2. Curation

- [x] 2.1 `zebra_agent_web/values_taxonomy.py`: list, promote, reject, demote, merge, prune, and the suggestion threshold
- [x] 2.2 `manage.py values_taxonomy` subcommands
- [x] 2.3 `/profile/taxonomy/` page, action POST endpoint and nav link
- [x] 2.4 `VALUES_TAG_PROMOTION_THRESHOLD` setting

## 3. Tests & docs

- [x] 3.1 Unit tests: transitions, merge, prune, record redirect (Django and in-memory), command, page
- [x] 3.2 Update `specs/zebra-as-is.md`
