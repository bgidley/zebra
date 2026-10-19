## Why

The Anthropic balance ran out and blocked prod; OpenRouter is cheaper and already wired in
(#204). Keeping four providers, vendor model names (haiku/sonnet/opus) and hand-kept price tables
is complexity Zebra no longer needs. Closes #205.

## What Changes

- **One backend**: OpenRouter. Anthropic, Kimi and OpenAI providers, the provider registry,
  provider names (`ZEBRA_LLM_PROVIDER`, `__llm_provider_name__`, task `provider`) and the
  anthropic SDK are removed.
- **Tiers, not models**: `low` / `medium` (default) / `high` / `max`, sent to `openrouter/auto`
  at that auto-router cost tier. A `vendor/model` slug still names an exact model. Stored legacy
  names are read as tiers.
- **One entry point**: `get_llm(model, context)`; with a context every call records its
  OpenRouter-reported cost. Price tables and per-action cost helpers are deleted.
- Web form, API, CLI, commands, settings, built-in workflows, prompts and docs use tiers.

## Non-goals

- Model allow-lists, price caps, streaming.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Every LLM call goes through OpenRouter at a cost tier | No Anthropic/Kimi/OpenAI provider or SDK in the code or lockfile; prod logs show only `openrouter.ai` LLM requests; a request at each tier sends `openrouter/auto` with that `cost_tier` (test) |
| O2 | Vendor model names are gone from code, config, workflows and UI | Grep finds `haiku`/`sonnet`/`opus` only in the legacy-name table and its tests; the goal form, API and CLI offer `low`/`medium`/`high`/`max` |
| O3 | Spend is recorded for every LLM call | Tests: an action given a context records OpenRouter's reported cost and tokens; prod goals show non-zero `__total_cost__` matching OpenRouter usage |
| O4 | Goals stored before the change still run | `normalize_model` maps `haiku`/`sonnet`/`opus`/`claude-*` to tiers (tests); a prod goal or routine queued with an old name completes |
| O5 | Prod works end to end on the new layer | Master deploy and smoke pipeline green; a real goal completes on prod |
