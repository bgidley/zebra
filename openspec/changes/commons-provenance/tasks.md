> Branch: `f229/commons-provenance`. Reference `Refs #229` in commits (S2a only).

## 1. Provenance core

- [ ] 1.1 `zebra_agent/provenance.py`: canonical loader, `content_sha256`, strip/read block, `Exposure`, `next_block`
- [ ] 1.2 `WorkflowLibrary.save()`; `add_workflow` delegates; `get_workflow_yaml` strips; `WorkflowInfo.commons`; owner + sphere attributes

## 2. Writers

- [ ] 2.1 `save_workflow_file` delegates to the library; optimizer passes its exposure, records a save-time leak rejection as a failed change
- [ ] 2.2 Gym promotion saves through the library with the candidate's exposure
- [ ] 2.3 Creator / variant creator pass exposure (`__user_id__`) and parent
- [ ] 2.4 Analyzer `run_user_ids` (incl. continuation chains) → evaluator `run_exposure_users`

## 3. Web + export gate

- [ ] 3.1 `api/commons_owner.py`: owner (S1 field or first user) and sphere onto the library
- [ ] 3.2 `commons_exportable()` refuses `foreign_users` (after rebasing onto S0)

## 4. Tests and docs

- [ ] 4.1 Unit tests for O1–O4
- [ ] 4.2 `specs/zebra-as-is.md`, `specs/zebra-commons-design.md`, package AGENTS.md
