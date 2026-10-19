## ADDED Requirements

### Requirement: LLM spend ledger
Every LLM call made through `get_llm(model, context)` SHALL append one ledger entry with its
OpenRouter-reported cost, input and output tokens, model and process id to the injected metrics
store. A failing ledger write SHALL be logged and SHALL NOT fail the call.

#### Scenario: Call recorded
- **WHEN** an action's LLM call reports cost 0.25 with 10 input and 5 output tokens
- **THEN** the ledger gains one entry with those values and the action's process id

#### Scenario: Ledger down
- **WHEN** the ledger write raises
- **THEN** the call still returns its response and a warning is logged

### Requirement: Budget from the ledger
`get_total_cost_since(since)` SHALL return the sum of ledger entries at or after `since`,
counting spend from goals, Dream Cycle, routines and every other workflow exactly once.

#### Scenario: Calls across a process tree
- **WHEN** a workflow makes two LLM calls and its subflow one, each costing 0.25
- **THEN** the budget's spend is 0.75

#### Scenario: Reset boundary
- **WHEN** entries fall just before, at and after the reset instant
- **THEN** only the entries at or after it are counted

### Requirement: Run records show full spend
When a goal finishes, its `WorkflowRun` cost and tokens SHALL be set to the ledger totals of
its root process and all descendants; a store without a ledger SHALL use the root's
`__total_cost__` plus the goal workflow's reported cost.

#### Scenario: Goal finished by the daemon
- **WHEN** the daemon records a finished goal whose processes spent 0.03 in the ledger
- **THEN** its run record's cost is 0.03

#### Scenario: Store without a ledger
- **WHEN** the metrics store keeps no ledger
- **THEN** the run's cost is the root's `__total_cost__` plus `execution_result.cost`
