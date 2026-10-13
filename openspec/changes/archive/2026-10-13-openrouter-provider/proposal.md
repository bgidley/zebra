## Why

Zebra can only reach Anthropic, OpenAI and Kimi directly. OpenRouter gives one key and one
OpenAI-compatible API for hundreds of models, so Zebra can try other models (or route around an
outage) without a new provider per vendor (#182).

## What Changes

- New `openrouter` LLM provider (`OpenRouterProvider`, an `OpenAIProvider` subclass) registered
  in the provider registry; `ZEBRA_LLM_PROVIDER=openrouter` makes it the server default.
- Model resolution: `haiku`/`sonnet`/`opus` (and their `claude-*-5-5` ids) map to
  `anthropic/claude-*-5.5`; raw `vendor/model` slugs pass through; anything else uses
  `OPENROUTER_MODEL` or `anthropic/claude-sonnet-5.5`.
- Cost: OpenRouter's reported `usage.cost` is carried on `TokenUsage.cost_usd`; a new
  `pricing.usage_cost()` prefers it over the price tables at every cost-tracking site.
- `zebra goal` / `manage.py run_goal` accept `--model openrouter`.
- Deploy copies `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` CI variables into `prod.env`.

## Capabilities

### New Capabilities
- `openrouter-provider`: run LLM calls through OpenRouter with provider-reported cost.

### Modified Capabilities
- `single-host-deployment`: `OPENROUTER_*` secrets added to `prod.env`.

## Impact

`zebra-tasks/zebra_tasks/llm/` (providers, base, models, pricing), cost call sites in
`llm/action.py`, `agent/curator.py`, `knowledge/review.py`; `zebra-agent-web` CLI and
`run_goal`; `scripts/deploy-podman.sh`; docs.
