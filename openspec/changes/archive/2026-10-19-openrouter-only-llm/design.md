## Context

#204 moved prod to OpenRouter by configuration while keeping four providers and vendor model
names. This change makes OpenRouter the only backend and tiers the only model vocabulary. Full
design: `specs/openrouter-llm-design.md`.

## Decisions

- **Interfaces**: `zebra_tasks.llm.client.get_llm(model, context)`, `model_for(task, context,
  default)`, `set_llm_factory()`; `zebra_tasks.llm.models.TIERS` / `DEFAULT_TIER` /
  `normalize_model`; `zebra_tasks.llm.openrouter.OpenRouterLLM`; `zebra_tasks.llm.usage.record_usage`.
  `LLMProvider` keeps only `complete()` and `model`.
- **Tier → request**: `model: openrouter/auto`, `extra_body.plugins: [{id: auto-router,
  cost_tier: <tier>}]`. Slugs pass through without the plugin. 4096 tokens of reasoning headroom
  on every request.
- **Cost**: recorded by the LLM returned from `get_llm` when given a context. Removes the
  per-action helpers and the `complete_json(on_response=)` hook, and counts calls that were
  never counted before.
- **Legacy**: `normalize_model` reads `haiku`/`kimi*` → low, `sonnet` → medium, `opus` → high;
  unknown → medium with a warning. Built-in workflows bumped so prod refreshes its copies.
- **Degrade**: actions that never fail catch `get_llm`'s `ValueError` (no API key).
- **Data model**: none; `__llm_provider_name__` is no longer written.
- **API**: `--model` / `model` choices are tiers in the CLI, `run_goal`, `run_workflow`, REST
  serializers and the goal form. `AgentLoop(provider=)` removed.

## Risks / trade-offs

- Per-prompt model choice varies quality; JSON steps retry via `complete_json`.
- Tests that patched module `get_provider` now patch `get_llm` or use the factory.

## as-is updates

`specs/zebra-as-is.md` LLM provider bullet replaced; new `specs/openrouter-llm-design.md`.
