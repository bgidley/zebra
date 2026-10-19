# OpenRouter-only LLM layer (#205, #204)

## 1. Goal and scope

Every LLM call goes through OpenRouter, and Zebra asks for a cost **tier** instead of a vendor
model. OpenRouter's auto router picks the model per prompt inside the tier's price band, which
is cheaper than pinning Claude and removes the per-vendor providers, names and price tables.
Issues [#204](https://gitlab.com/gidley/zebra/-/work_items/204) (switch prod to OpenRouter) and
[#205](https://gitlab.com/gidley/zebra/-/work_items/205) (this refactor).

Not in scope: per-task allow-lists of models, `max_price` caps, streaming (nothing used it).

## 2. Data model

No tables. Process property `__llm_model__` holds a tier (`low` / `medium` / `high` / `max`) or
a `vendor/model` slug. `__llm_provider_name__` and `__llm_provider__` are no longer written or
read. Cost properties (`__total_cost__`, `__total_tokens__`, `__token_history__`) are unchanged;
their values now come from OpenRouter's reported `usage.cost`.

Legacy values stored before #205 (`haiku`, `sonnet`, `opus`, `claude-*`, `kimi*`) are read as
their tier by `normalize_model()` (haiku/kimi → low, sonnet → medium, opus → high); nothing writes
them. Unknown names fall back to `medium` with a warning.

## 3. Interfaces

| Piece | What it is |
|---|---|
| `zebra_tasks/llm/models.py` | `TIERS`, `DEFAULT_TIER = "medium"`, `normalize_model(name)` |
| `zebra_tasks/llm/client.py` | `get_llm(model=None, context=None)`: the only way to get an LLM; with a context each call's usage is recorded on its process. `model_for(task, context, default)`. `set_llm_factory(factory)`: test seam, reset by the root `conftest.py` after every test |
| `zebra_tasks/llm/openrouter.py` | `OpenRouterLLM`: tier → `model: openrouter/auto` + `plugins: [{id: auto-router, cost_tier: <tier>}]`; slug → `model: <slug>`. `REASONING_HEADROOM_TOKENS` (4096) added to `max_tokens`. OpenAI SDK, `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` |
| `zebra_tasks/llm/usage.py` | `record_usage(context, response)`: tokens, cost, history, soft budget warning |
| `LLMProvider` (base) | `complete()` and `model` only (`stream`, `name`, `max_context_tokens` removed) |
| `complete_json` | `on_response` removed (cost is recorded by the LLM itself) |
| `AgentLoop(model=...)` | `provider=` removed |
| CLI / `run_goal` / `run_workflow` / API / goal form | `--model` / `model` choices are the tiers |

Removed: `zebra_tasks/llm/providers/` (Anthropic, Kimi, OpenAI, OpenRouter providers and the
registry), `pricing.py`, `_testing.py` (unused cassette provider), `ZEBRA_LLM_PROVIDER` /
`LLM_PROVIDER`, `OPENROUTER_ROUTING`, `OPENROUTER_MODEL`, the `anthropic` extra and SDK.

## 4. Control flow

An action calls `get_llm(model_for(task, context, default), context).complete(...)`. The
returned LLM records usage after each call, so actions no longer track cost themselves; this
also closes a gap where selector, creator, assess_and_record and others never counted their
spend. Actions that must never fail (curator, knowledge review, improvement requests) catch the
`ValueError` `get_llm` raises without an API key and degrade as before.

The plan-review ethics gate is given the planned workflow's description, `use_when` and steps
from the library rather than only its name (#204), so a cheaper or different model does not
reject a correct plan for an unlucky name.

## 5. Configuration

`OPENROUTER_API_KEY` (CI variable → prod.env), `ZEBRA_LLM_MODEL` (server default tier, prod
`medium` in `site.env`), `ZEBRA_LLM_TIMEOUT_SECONDS` (unchanged).

## 6. Open questions / risks

- The auto router's choice varies per prompt, so quality varies more than with one pinned
  model. JSON-replying steps already retry through `complete_json`; the selector, ethics gates
  and creator do their own parsing.
- Reasoning models can spend a small `max_tokens` on thinking; the 4096-token headroom covers
  it, at no cost for unused tokens.
