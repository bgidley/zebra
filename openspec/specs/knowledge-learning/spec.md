# knowledge-learning Specification

## Purpose
The agent learns durable personal knowledge about the user from goal runs (F152, #152): LLM extraction, agent-sourced storage, contradiction routing, and review on `/knowledge/`.

## Requirements

### Requirement: Extract knowledge candidates from a goal run
The system SHALL provide an `extract_knowledge` task action that asks an LLM for durable personal facts about the user from the goal text, the user's human-task answers, the continuation comment and the run result. It SHALL return candidates `{category, key, value, time_sensitive, confidence}` without writing to the knowledge store. Categories SHALL be limited to `KNOWLEDGE_CATEGORIES` and keys SHALL be normalised to snake_case, with filler prefixes such as `user_` / `my_` dropped. Existing keys for the user SHALL be included in the prompt so the LLM can reuse them. Provider errors and unparseable responses SHALL yield no candidates and SHALL NOT fail the task. The action SHALL route `has_candidates` or `no_candidates`.

#### Scenario: No user
- **WHEN** the process has no `__user_id__`
- **THEN** no LLM call is made and the action routes `no_candidates`

#### Scenario: Personal fact stated in the goal
- **WHEN** the goal is "I work at Acme, plan my commute" and the LLM returns `{"category": "facts", "key": "Employer", "value": "Acme"}`
- **THEN** the candidate has key `employer` and the action routes `has_candidates`

#### Scenario: LLM failure
- **WHEN** the provider raises or returns non-JSON
- **THEN** the action succeeds with no candidates

### Requirement: Privacy guardrails on extracted knowledge
`extract_knowledge` SHALL always drop candidates whose key or value looks like a credential or a card/account number. It SHALL drop candidates the LLM marks `sensitive` (special-category data) unless `allow_sensitive` is true or `ZEBRA_KNOWLEDGE_ALLOW_SENSITIVE` is set. It SHALL drop candidates below `min_confidence`, duplicate `(category, key)` pairs, and anything beyond `max_entries`.

#### Scenario: Sensitive fact without opt-in
- **WHEN** a candidate is marked `sensitive: true` and no opt-in is set
- **THEN** it is dropped with reason `sensitive`

#### Scenario: Password
- **WHEN** a candidate's key is `wifi_password`
- **THEN** it is dropped with reason `secret`, even with the opt-in set

### Requirement: Store learned knowledge as agent-sourced
The system SHALL provide a `store_learned_knowledge` action. It SHALL store each candidate with `source="agent"` and `confidence = min(candidate confidence, max_confidence)`, where `max_confidence` defaults to 0.5. It SHALL use the same contradiction rules as `add_knowledge`, store at most `max_entries` candidates, and skip when there is no `__user_id__` or no knowledge store.

#### Scenario: New fact
- **WHEN** a candidate has no existing entry for `(user, category, key)`
- **THEN** an entry with `source="agent"` and confidence ≤ 0.5 is created

#### Scenario: Re-observed fact
- **WHEN** the same value is already stored
- **THEN** `last_verified` is refreshed and confidence becomes `max(old, new)`, without being raised to 1.0

### Requirement: Contradictions go to the user
When a candidate's value differs from the stored value, `store_learned_knowledge` SHALL NOT modify the stored entry, whatever its source. It SHALL instead create and start a "Resolve Knowledge Contradiction" process. That process SHALL carry `__user_id__`, `entry_id`, `category`, `key`, `existing_value` and `proposed_value`. No second process SHALL be started while an identical conflict is still running.

#### Scenario: Conflicting fact in a later goal
- **WHEN** a human entry `employer=Acme` exists and a goal run extracts `employer=Globex`
- **THEN** the entry still reads `Acme`, and a RUNNING resolution process waits on its `present_contradiction` human task

#### Scenario: User accepts the new value
- **WHEN** the user resolves with `use_new`
- **THEN** the entry's value is updated, its confidence becomes 1.0 and its source becomes `human`

### Requirement: Agent main loop learns after each run
`agent_main_loop.yaml` SHALL run `extract_knowledge` and then `store_learned_knowledge` after the post-execution ethics review and before `report_outcome`, for both successful and failed goal runs. `execute_goal_workflow` SHALL include the child's human-task answers, without read-only fields, as `user_inputs` in its result.

#### Scenario: Nothing personal
- **WHEN** a goal contains nothing personal
- **THEN** the loop completes with no knowledge entries written

### Requirement: Review learned knowledge on /knowledge/
The `/knowledge/` page SHALL show each entry's source and confidence and SHALL hide soft-deleted entries. For entries that are not human-sourced at confidence 1.0, it SHALL offer a Confirm action. `POST /knowledge/<id>/confirm/` SHALL set confidence 1.0 and source `human` on the current user's entry, and SHALL return 404 for another user's entry.

#### Scenario: Confirm an agent entry
- **WHEN** the user confirms an agent entry at confidence 0.5
- **THEN** the entry has confidence 1.0 and source `human`
