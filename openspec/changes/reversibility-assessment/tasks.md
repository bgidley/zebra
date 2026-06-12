# Tasks — reversibility-assessment (branch f14/reversibility-assessment, GitLab #14)

## 1. Hints and registry (zebra-py)

- [x] 1.1 Add `reversibility_hint: ClassVar[str] = "context_dependent"` to `TaskAction`
      and `reversibility_hint` field to `ActionMetadata` / `get_metadata()`
      (`zebra-py/zebra/tasks/base.py`)
- [x] 1.2 Add `list_reversibility_hints()` and `get_action_class()` to `ActionRegistry`
      (`zebra-py/zebra/tasks/registry.py`)
- [x] 1.3 zebra-py tests: hint default, metadata round-trip, registry queries

## 2. Assessor (zebra-tasks)

- [x] 2.1 Create `zebra_tasks/agent/reversibility.py`: `ReversibilityAssessment`
      dataclass + `to_dict()`, `assess_reversibility(...)` with hint short-circuit,
      LLM path (haiku default, get_provider pattern, JSON-only, chain-of-consequences /
      dropped-weight / anti-gaming prompt), fail-closed on provider/parse errors
- [x] 2.2 Unit tests `zebra-tasks/tests/test_reversibility.py`: hint short-circuits
      (no provider call), reversible/irreversible LLM JSON, code-fence stripping,
      parse error → fail closed, provider error → fail closed, prompt contains concrete
      parameters and declared reversibility

## 3. trust_gate integration (zebra-tasks)

- [x] 3.1 Update `trust_gate.py`: `target_task_id` + `model` inputs; SEMI_AUTONOMOUS
      always assesses (declaration is context only); resolve target task definition via
      `context.process_definition` and action class via
      `context.engine.actions.get_action_class`; fail closed without assessable input;
      append assessment to `__trust_assessments__` and embed in decision record
- [x] 3.2 Update `zebra-tasks/tests/test_trust_gate.py` SEMI_AUTONOMOUS cases for the
      new behaviour; assert SUPERVISED/AUTONOMOUS perform no assessment
- [x] 3.3 Set `reversibility_hint = "always_reversible"` on `FileReadAction`,
      `FileInfoAction`, `FileSearchAction`, `LLMCallAction`

## 4. E2E (issue #14 criterion)

- [x] 4.1 Extend `zebra-tasks/tests/test_trust_gate_e2e.py`: gate with
      `target_task_id=delete_files` → `file_delete`; mocked provider classifies by path;
      `/etc/zebra/prod.conf` → irreversible → pauses at approval task; `/tmp/...` →
      reversible → proceeds and file is deleted without approval

## 5. Docs and verification

- [x] 5.1 Update `zebra-tasks/AGENTS.md` (TrustGateAction + reversibility module + file
      table), root `AGENTS.md` new-action checklist (mention `reversibility_hint`),
      `specs/zebra-as-is.md` trust paragraph + F12–F17 status table
- [x] 5.2 Full local suite:
      `uv run pytest --ignore=zebra-agent-web/tests/e2e_live --ignore=zebra-agent-web/tests/e2e -q`
- [x] 5.3 `uv run ruff check --fix . && uv run ruff format .`

## 6. Feedback, commit, CI

- [x] 6.1 `bash scripts/zebra-feedback.sh 14 "Contextual reversibility assessment" "<changes>"`
- [ ] 6.2 Commit (`feat: add contextual reversibility assessment` … `Closes #14`), push,
      verify GitLab pipeline green
- [ ] 6.3 Archive change (sync new spec + apply trust-gate MODIFIED delta), GitHub PR,
      merge to master, verify deploy + smoke, confirm issue #14 closed
