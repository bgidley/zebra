## ADDED Requirements

### Requirement: One builder for the selector's workflow list
Every path that creates an Agent Main Loop process (`AgentLoop.process_goal`, the web/daemon `queue_goal` helper, and the `queue_goal` task action) SHALL build `available_workflows` with `list_goal_workflows`, which returns one dict per library workflow with `name`, `description`, `tags`, `success_rate` (float 0.0–1.0), `use_count` and `use_when`, excluding every workflow tagged `system`.

#### Scenario: System-tagged workflow excluded on the direct path
- **WHEN** the library contains a workflow tagged `system` that is not named "Agent Main Loop" (e.g. "Knowledge Decay") and a goal is processed via `AgentLoop.process_goal`
- **THEN** that workflow is not in the process's `available_workflows`

#### Scenario: Entry points agree
- **WHEN** the same library is used to queue a goal via `queue_goal` and to start one via `process_goal`
- **THEN** both processes get identical `available_workflows`

### Requirement: Selector uses the current library
`workflow_selector` SHALL build its candidate list from the live workflow library when one is available in the execution context, and SHALL fall back to its `available_workflows` input when no library is available or listing fails.

#### Scenario: Workflow added after queueing
- **WHEN** a goal is queued, a new non-system workflow is then added to the library, and the daemon runs the goal
- **THEN** the selector's candidates include the new workflow

#### Scenario: No library available
- **WHEN** the execution context has no workflow library
- **THEN** the selector uses the `available_workflows` input unchanged

### Requirement: Never-run workflows show N/A success
The selector prompt SHALL show success as "N/A" for a workflow whose `use_count` is 0, and as a percentage otherwise.

#### Scenario: New workflow
- **WHEN** a candidate workflow has `use_count` 0
- **THEN** its prompt line reads `success: N/A`

### Requirement: Queued goals use the configured LLM provider
The web/daemon `queue_goal` helper SHALL set `__llm_provider_name__` from the configured `LLM_PROVIDER` setting.

#### Scenario: Non-default provider
- **WHEN** `ZEBRA_AGENT_SETTINGS["LLM_PROVIDER"]` is `"openai"` and a goal is queued
- **THEN** the process's `__llm_provider_name__` is `"openai"`
