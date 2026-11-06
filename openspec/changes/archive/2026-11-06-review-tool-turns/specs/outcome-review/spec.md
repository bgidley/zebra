## ADDED Requirements

### Requirement: The review starts from a change map
`scripts/zebra-outcome-review.sh` SHALL send a `change_map` input listing every changed file with
its added and removed line counts, then the test functions the diff adds or changes, grouped by
file, capped at 8000 characters. The Outcome Review prompt SHALL show it before the diff.

#### Scenario: Map of a change with tests
- **WHEN** the reviewed diff changes `a.py` and adds `test_one` and `test_two` to `tests/test_a.py`
- **THEN** `change_map` lists both files with their `+`/`-` counts and names both tests under `tests/test_a.py`

#### Scenario: Map survives a cut diff
- **WHEN** the diff is longer than `MAX_DIFF_CHARS`
- **THEN** `change_map` still lists every changed file

### Requirement: The review has a tight tool budget
The Outcome Review `zebra_review` step SHALL allow at most 8 tool turns and `zebra_reconsider` at
most 5, both with `answer_on_budget`, and their system prompts SHALL tell the agent to start from
the change map, read line ranges rather than whole files, and ask for several reads in one turn.

#### Scenario: Budget limits
- **WHEN** the Outcome Review workflow is loaded
- **THEN** `zebra_review.max_tool_turns` is 8 and `zebra_reconsider.max_tool_turns` is 5
