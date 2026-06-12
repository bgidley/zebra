# Tasks — trust-gate (branch f13/trust-gate, GitLab #13)

## 1. Action implementation (zebra-tasks)

- [x] 1.1 Create `zebra-tasks/zebra_tasks/agent/trust_gate.py`: `TrustGateAction` with
      `description`, `inputs`/`outputs` ParameterDefs, level→route logic (string
      comparison against SUPERVISED/SEMI_AUTONOMOUS/AUTONOMOUS, fail-closed default),
      user_id resolution (task property → `__user_id__`), decision record appended to
      `__trust_gate_decisions__` and returned as output
- [x] 1.2 Register entry point `trust_gate = "zebra_tasks.agent.trust_gate:TrustGateAction"`
      in `zebra-tasks/pyproject.toml`, run `uv sync --all-packages`

## 2. Unit tests (zebra-tasks)

- [x] 2.1 Unit tests in `zebra-tasks/tests/test_trust_gate.py` covering every spec
      scenario: SUPERVISED→approve, AUTONOMOUS→proceed, SEMI_AUTONOMOUS×(reversible→
      proceed, irreversible/absent→approve), missing store→approve+warning, missing
      user_id→approve, missing domain→fail, decision audit accumulation, template
      resolution of user_id/action_description

## 3. E2E pause/resume test

- [x] 3.1 Engine-level test (`zebra-tasks/tests/test_trust_gate_e2e.py`): workflow YAML
      with trust_gate → (approve) human task (auto: false) → execute step, and
      (proceed) direct path; run with InMemoryStore + InMemoryTrustStore in extras;
      assert SUPERVISED pauses at READY human task, `complete_task` resumes to
      COMPLETE; assert AUTONOMOUS path skips the human task entirely

## 4. Docs and verification

- [x] 4.1 Update `specs/zebra-as-is.md` trust-model item + status table (F13 implemented)
      and `zebra-tasks/AGENTS.md` action reference table
- [x] 4.2 Run full local suite:
      `uv run pytest --ignore=zebra-agent-web/tests/e2e_live --ignore=zebra-agent-web/tests/e2e -q`
- [x] 4.3 Run `uv run ruff check --fix . && uv run ruff format .`

## 5. Feedback, commit, CI

- [x] 5.1 Run Zebra feedback: `bash scripts/zebra-feedback.sh 13 "trust_gate task action" "<changes>"`
- [ ] 5.2 Commit (`feat: add trust_gate task action` … `Closes #13`), push
      `f13/trust-gate`, verify GitLab pipeline green
- [ ] 5.3 Archive the change (sync spec), open GitHub PR, merge to master per CLAUDE.md
      workflow, verify deploy + smoke pass, confirm issue #13 closed
