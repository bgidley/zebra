> Branch: `f229/commons-provenance`. Reference `Refs #229` in commits (S2a only).

## 1. Provenance core

- [x] 1.1 `zebra_agent/provenance.py`: canonical loader, `content_sha256`, strip/read block, `Exposure`, `next_block`
- [x] 1.2 `WorkflowLibrary.save()`; `add_workflow` delegates; `get_workflow_yaml` strips; `WorkflowInfo.commons`; owner + sphere attributes

## 2. Writers

- [x] 2.1 `save_workflow_file` delegates to the library; optimizer passes its exposure, records a save-time leak rejection as a failed change
- [x] 2.2 Gym promotion saves through the library with the candidate's exposure
- [x] 2.3 Creator / variant creator pass exposure (`__user_id__`) and parent
- [x] 2.4 Analyzer `run_user_ids` (incl. continuation chains) → evaluator `run_exposure_users`
- [x] 2.5 Optimizer folds the taint of shown workflows (`existing_workflows`, `definitions_shown`) into its exposure (`Exposure.with_shown`, review fix)

## 3. Web + export gate

- [x] 3.1 `api/commons_owner.py`: owner (S1 field or first user) and sphere onto the library
- [x] 3.2 `commons_exportable()` refuses `foreign_users` (after rebasing onto S0)

## 4. Tests and docs

- [x] 4.1 Unit tests for O1–O5 (`zebra-agent/tests/test_provenance.py`, `zebra-tasks/tests/test_commons_provenance_writers.py`, `zebra-agent-web/tests/unit/test_commons_owner.py`)
- [x] 4.2 `specs/zebra-as-is.md`, `specs/zebra-commons-design.md`, package AGENTS.md
