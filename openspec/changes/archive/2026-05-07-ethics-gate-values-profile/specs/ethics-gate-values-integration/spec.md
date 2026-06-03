## ADDED Requirements

### Requirement: Values profile is optionally incorporated into ethics evaluation

When `EthicsGateAction` receives a `user_id` input AND `__profile_store__` is available in `context.extras`, it SHALL load the user's current `ValuesProfile` via `ProfileStore.get_current(user_id)` and include the profile text in the LLM prompt alongside the Kantian evaluation.

#### Scenario: Gate with user_id and existing profile consults profile

- **WHEN** `EthicsGateAction` runs with `user_id` set and the profile store returns a current version
- **THEN** the LLM prompt includes the user's `core_values_text`, `ethical_positions_text`, `priorities_text`, and `deal_breakers_text`

#### Scenario: Gate without user_id skips profile loading

- **WHEN** `EthicsGateAction` runs with no `user_id` property
- **THEN** the action performs a Kantian-only evaluation, identical to current behaviour

#### Scenario: Gate with user_id but no existing profile falls back to Kantian-only

- **WHEN** `EthicsGateAction` runs with `user_id` set but `ProfileStore.get_current()` returns `None`
- **THEN** the action performs a Kantian-only evaluation and logs at INFO level that no profile was found

#### Scenario: Gate with user_id but missing profile store falls back to Kantian-only

- **WHEN** `EthicsGateAction` runs with `user_id` set but `__profile_store__` is absent from `context.extras`
- **THEN** the action performs a Kantian-only evaluation and logs a warning

### Requirement: Kantian rejection takes precedence over values approval

The final `approved` verdict SHALL be computed by Python precedence logic, not delegated to the LLM. Kantian rejection SHALL always override a values-based approval. Values rejection SHALL block a Kantian-approved goal.

The rule is: `approved = kantian_approved AND (values_approved if profile_loaded else True)`.

#### Scenario: Kantian rejects, values approves — final is reject

- **WHEN** the Kantian evaluation returns `approved: false` and the values assessment returns `approved: true`
- **THEN** the final `approved` in the stored assessment and `next_route` are `false` / `"reject"`

#### Scenario: Kantian approves, values rejects — final is reject

- **WHEN** the Kantian evaluation returns `approved: true` and the values assessment returns `approved: false`
- **THEN** the final `approved` in the stored assessment and `next_route` are `false` / `"reject"`

#### Scenario: Both approve — final is approve

- **WHEN** both the Kantian evaluation and the values assessment return `approved: true`
- **THEN** the final `approved` in the stored assessment is `true` and `next_route` is `"proceed"`

### Requirement: Combined assessment schema

The stored assessment (written to the process property identified by `output_key`) SHALL include a `values_assessment` key in addition to the existing Kantian fields.

When a profile was loaded, `values_assessment` SHALL be an object with:
- `approved` (bool): whether the goal aligns with the user's values
- `reasoning` (string): LLM reasoning for the values verdict
- `conflicts` (list of strings): specific value conflicts if `approved` is false

When no profile was loaded, `values_assessment` SHALL be `null`.

#### Scenario: Assessment includes values_assessment when profile loaded

- **WHEN** `EthicsGateAction` runs with a user profile present and evaluation completes
- **THEN** the stored assessment dict contains a `values_assessment` key with `approved`, `reasoning`, and `conflicts` fields

#### Scenario: Assessment has null values_assessment when no profile

- **WHEN** `EthicsGateAction` runs without a `user_id` (Kantian-only path)
- **THEN** the stored assessment dict contains `"values_assessment": null`

### Requirement: Both evaluator verdicts are logged

The action SHALL log both the Kantian and values verdicts at INFO level, so the reasoning is visible in workflow logs without reading stored process properties.

#### Scenario: Log shows both verdicts when profile was consulted

- **WHEN** a values-informed ethics gate completes evaluation
- **THEN** the log at INFO level contains the Kantian `approved` flag, the values `approved` flag, and the `overall_reasoning` summary

#### Scenario: Log shows Kantian-only verdict when no profile

- **WHEN** a Kantian-only ethics gate completes evaluation
- **THEN** the log at INFO level contains the Kantian `approved` flag and `overall_reasoning`, without reference to a values assessment
