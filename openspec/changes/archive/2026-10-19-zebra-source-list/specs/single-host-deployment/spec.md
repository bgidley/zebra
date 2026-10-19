## ADDED Requirements

### Requirement: Image ships the project docs Zebra reads
The runtime image SHALL contain `specs/`, `docs/`, `openspec/`, `scripts/`, `deploy/` and the root
`*.md` files under `/app`, so `zebra_source` can read the docs and scripts that agent prompts name.
It SHALL NOT contain `.env`, `.git` or anything else `.dockerignore` excludes.

#### Scenario: Docs readable on prod
- **WHEN** *Read Zebra Source* reads `specs/zebra-as-is.md`, `AGENTS.md` or `scripts/zebra-outcome-review.sh` on prod
- **THEN** it returns the file's lines
