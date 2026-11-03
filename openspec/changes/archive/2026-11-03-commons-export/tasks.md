> Branch: `f229/commons-export`. Reference `Refs #229` in commits (S2b).

## 1. Definition ids

- [x] 1.1 Loader derives `c:` ids from `commons.content_sha256`; legacy ids unchanged
- [x] 1.2 Tests in `zebra-py` and `zebra-agent`

## 2. Adoption

- [x] 2.1 `WorkflowLibrary.save(writer="adopt", received=, expected_sha256=, origin_pubkey=)`; `relabel()` + `adopted_block()` in provenance
- [x] 2.2 Tests: hash kept, no `llm-defined`, mismatch and taken-name refusals, idempotent re-adopt

## 3. Signed export

- [x] 3.1 `zebra_agent/commons/export.py`: `build_export`, `export_workflow`, `verify_export`
- [x] 3.2 Web glue `api/commons_export.py` + `manage.py commons_export` / `commons_import [--adopt]`
- [x] 3.3 Tests: verifies, byte-flip loop fails, revoked / uncertified / foreign / mismatch fail, non-exportable refused; command tests

## 4. Sharing trust domain

- [x] 4.1 `sharing` in `DEFAULT_DOMAINS`; trust gate reads the owner's level for owner-governed domains
- [x] 4.2 Tests

## 5. Personal-data scan

- [x] 5.1 `zebra_tasks/commons/pii_scan.py` (`commons_pii_scan`), entry point
- [x] 5.2 Tests: rules, golden tasks, LLM finding, LLM failure fails closed, clean

## 6. Docs

- [x] 6.1 `specs/zebra-as-is.md`, `specs/zebra-commons-design.md`, package AGENTS.md
