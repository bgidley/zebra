## ADDED Requirements

### Requirement: Dream cycle requests improvements to Zebra itself
The Dream Cycle SHALL run a `propose_zebra_improvements` step after the knowledge review that gives an LLM the cycle's evaluation (key issues, improvement priorities), continuation capability gaps and rejected optimizer changes, and asks only for problems that need a change to Zebra's code (engine, task actions, web UI), not a workflow edit. Each accepted proposal SHALL start a *Zebra Improvement Request* process carrying the title, area, problem, evidence, suggested change, impact and the dream cycle's process id.

#### Scenario: Code-level gap becomes a request
- **WHEN** the optimizer rejected a change because a needed action does not exist and the LLM proposes an improvement for it
- **THEN** a *Zebra Improvement Request* process is running with a review task, and the step output lists it with its process id

#### Scenario: Nothing to analyse
- **WHEN** the cycle has no key issues, priorities, capability gaps or rejected changes
- **THEN** no LLM call is made and no request is started

### Requirement: Requests are few and not repeated
The step SHALL start at most `max_requests` (default 2) requests per cycle. It SHALL NOT start a request whose normalised title matches an earlier *Zebra Improvement Request* process in any state, and SHALL show the earlier titles to the LLM.

#### Scenario: Cap
- **WHEN** the LLM proposes more requests than `max_requests`
- **THEN** only the first `max_requests` are started

#### Scenario: Duplicate of an earlier request
- **WHEN** a proposal's title matches an earlier request, ignoring case and punctuation
- **THEN** no new process is started and the proposal is reported as skipped

### Requirement: Human reviews each request
A *Zebra Improvement Request* SHALL wait on one human task whose form shows the request and records a verdict (`accepted`, `rejected`, `duplicate`, `later`), an optional issue link and notes. It SHALL be a system workflow, never picked by the goal selector.

#### Scenario: Review recorded
- **WHEN** the human submits the review with verdict `accepted` and an issue link
- **THEN** the process completes and `/dreams/` shows the request as accepted with the link

### Requirement: The step never fails the cycle
Missing provider or workflow library, LLM errors or unparseable output SHALL produce an empty result with the error recorded, and the cycle SHALL continue to the summary, which reports the requests made.

#### Scenario: LLM returns garbage
- **WHEN** the LLM response is not valid JSON
- **THEN** the step succeeds with no requests and an error entry, and the summary still runs
