## MODIFIED Requirements

### Requirement: Every action declares its reversibility hint
Every action registered through the `zebra.tasks` entry points or zebra-py's default actions SHALL
set `reversibility_hint` on its own class; a hint inherited from a base class SHALL NOT count. An
action SHALL be `always_reversible` only if its effects stay within the running process (reads,
LLM calls, pure transforms, gates, audit appends). Actions that write files, stores, the workflow
library or the goal queue, run code, start child workflows, or submit a builder job (which can
push or merge code) SHALL NOT be `always_reversible`.

#### Scenario: No inherited default
- **WHEN** the hint test loads every registered action class
- **THEN** each defines `reversibility_hint` in its own class body, including every git action

#### Scenario: Writers are not reversible
- **WHEN** the hints of `file_write`, `file_copy`, `file_move`, `file_delete`, `python_exec`,
  `subworkflow`, `parallel_subworkflows`, `queue_goal`, `add_knowledge`,
  `store_learned_knowledge`, `save_values_profile`, `update_conceptual_memory`,
  `propose_trust_promotion` and `claude_code_build` are read
- **THEN** none is `always_reversible`

#### Scenario: Writers that were already hinted
- **WHEN** the hints of `review_knowledge`, `workflow_curator`, `propose_zebra_improvements`,
  `write_postmortem` and `claude_code_build` are read
- **THEN** none is `always_reversible`, and `unsafe_reason(..., strict=True)` refuses a workflow
  using any of them

#### Scenario: No always_reversible action writes unnoticed
- **WHEN** an `always_reversible` action's module calls a store write, a library write or a
  process start
- **THEN** the hint test fails unless the action is allowlisted with a reason

#### Scenario: No always_reversible action submits a build
- **WHEN** an `always_reversible` action's module calls `submit_build`
- **THEN** the hint test fails; there is no allowlist for builder jobs
