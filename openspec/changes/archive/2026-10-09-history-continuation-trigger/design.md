# Design

## Decision input
`AssessHistoryNeedAction` builds its classification text from:
- the goal
- `continuation_comment`, when set
- `previous_run_context.goal`, when set

The keys are the existing `followup.py` constants. When `previous_run_context` is present, the
regex pre-check is skipped: a continuation is always about past work, so a Haiku call is cheap
and justified. The extended cue regex still keeps ordinary goals free of LLM calls.

## Keyword matching
A shared helper, `search_keywords(text) -> list[str]` in `zebra_agent/storage/interfaces.py`:
- lowercases the text and splits it on non-word characters
- drops tokens shorter than 3 characters and a small stopword set
- de-duplicates while keeping order
- returns `[text]` when nothing is left

Both stores match runs whose goal contains **any** keyword (Django: OR of
`Q(goal__icontains=k)`). OR matching widens results, but they stay newest first and limited,
and `history_context` is already size-capped.

## Risks
- Wider matches can pull in loosely related runs. This is acceptable: the downstream LLM sees
  each run's goal and can ignore irrelevant ones.
