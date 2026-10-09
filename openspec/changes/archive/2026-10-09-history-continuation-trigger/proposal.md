# Proposal

Closes #150

## Why

The F138 workflow-history lookup never fires for continuations or "what next" goals. Run
`db777bc0` ("Our holiday plans continue - what next", continued with the comment "Check workflow
history") logged `needs_history: False — No history cues in goal` and never saw the earlier
"plan a holiday to Scotland next Easter" run.

- `assess_history_need` only regex-checks the goal. It ignores the continuation comment and
  `previous_run_context`, and its cues miss "continue", "what next", "pick up" and similar.
- `search_runs` matches the search text as one substring. The LLM returns "1-3 keywords", so
  "holiday plans" misses "plan a holiday to Scotland".

## What Changes

- `assess_history_need` also classifies the continuation comment and the previous run's goal, and
  always asks the LLM when the goal is a continuation. More cue phrases are added, and the prompt
  asks for topic keywords.
- `search_runs` (in-memory and Django stores) splits the text into keywords and matches runs whose
  goal contains any of them. Text that is all stopwords or short words falls back to matching the
  whole string.
- No change to the agent main loop YAML.

## Capabilities

### Modified Capabilities
- `workflow-history`: history-need decision considers continuations; text search matches any keyword.

## Impact

- `zebra-tasks/zebra_tasks/agent/history.py`
- `zebra-agent/zebra_agent/storage/interfaces.py`, `zebra-agent/zebra_agent/storage/metrics.py`
- `zebra-agent-web/zebra_agent_web/metrics_store.py`
