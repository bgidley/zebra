## ADDED Requirements

### Requirement: Routines can queue goals
A routine with a `goal` SHALL be dispatched by queueing that goal through the injected
`queue_goal_fn`, tagged with `__routine__`, instead of creating a workflow process. A routine SHALL
NOT queue a goal while a previous goal from the same routine, created less than 20 hours earlier, is
still `CREATED` or `RUNNING`.

#### Scenario: Goal routine due
- **WHEN** a routine with `goal` set becomes due
- **THEN** `queue_goal_fn` is called once with that routine
- **AND** the routine's next run is advanced

#### Scenario: Previous goal still pending
- **WHEN** a goal routine becomes due and a process with the same `__routine__` is `CREATED` or `RUNNING`
- **THEN** no new goal is queued and the run status is `already_queued`

#### Scenario: Stale pending goal
- **WHEN** a goal routine becomes due and its previous goal has been `RUNNING` for more than 20 hours
- **THEN** a new goal is queued

#### Scenario: No queue function
- **WHEN** a goal routine becomes due and no `queue_goal_fn` is configured
- **THEN** nothing is queued and a skip is logged

### Requirement: Goals can request a workflow
The workflow selector SHALL use the process property `requested_workflow` when it names a workflow
in the library, routing `use_existing` without calling the LLM.

#### Scenario: Requested workflow exists
- **WHEN** a goal process has `requested_workflow: "Daily News Reading"` and the library contains it
- **THEN** the selector selects it and routes `use_existing` with no LLM call

#### Scenario: Requested workflow missing
- **WHEN** the requested workflow is not in the library
- **THEN** normal LLM selection runs

### Requirement: Daily news reading
Zebra SHALL fetch the day's stories from news.kagi.com once a day, pick 5 to read, read them, write
a digest and store what it learned as `world` knowledge.

#### Scenario: Fetch stories
- **WHEN** `kagi_news_fetch` runs with categories
- **THEN** it returns compact stories with id, category, title, summary, talking points and source links

#### Scenario: Read picks with fallback
- **WHEN** `kagi_news_read` runs with picked story ids and extraction fails for one source
- **THEN** that story is read from its Kagi News summary and the task still succeeds

#### Scenario: Store world knowledge
- **WHEN** the workflow stores learned takeaways
- **THEN** they are saved as `category=world`, `source=agent` and time-sensitive

### Requirement: World knowledge updates in place
With `update_agent_entries` enabled, `store_learned_knowledge` SHALL update an existing
agent-sourced entry whose value changed, and SHALL still start contradiction resolution when the
existing entry is human-sourced.

#### Scenario: Developing story
- **WHEN** a `world` candidate conflicts with an agent-sourced entry
- **THEN** the entry's value is updated and no resolution process starts

#### Scenario: Human entry
- **WHEN** a candidate conflicts with a human-sourced entry
- **THEN** nothing is overwritten and a *Resolve Knowledge Contradiction* process starts
