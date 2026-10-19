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
| O1 | Every LLM call goes through OpenRouter at a cost tier, with defined defaults and errors | No inference SDK but OpenAI's client (for OpenRouter) in code or lockfile; tests: each tier sends `openrouter/auto` with that `cost_tier`, no model means `medium`, an unknown name means `medium` with a warning, a missing key raises `ValueError` naming `OPENROUTER_API_KEY`; a live call per tier returns an answer from a model in a rising price band |
| O2 | Vendor model names are gone from code, config, workflows and UI | Grep finds `haiku`/`sonnet`/`opus` only in the legacy-name table and its tests; the goal form, API and CLI offer `low`/`medium`/`high`/`max` |
| O3 | Spend is recorded for every LLM call made with a context | Tests: OpenRouter's reported cost and tokens land on the process; several calls accumulate; a call with no reported cost records 0; a call without a context records nothing |
| O4 | Goals stored before the change still run | `normalize_model` maps `haiku`/`sonnet`/`opus`/`claude-*` to tiers (tests); a prod goal or routine queued with an old name completes |
| O5 | A real prod goal completes on the new layer, its cost matching OpenRouter's | After deploy, a goal run on prod completes and its recorded `__total_cost__` equals the sum of the per-call costs OpenRouter reported (`__token_history__`), with smoke green |
