Branch: `f205/openrouter-only`

## 1. LLM layer

- [x] 1.1 `models.py` tiers + `normalize_model`; `openrouter.py` `OpenRouterLLM` (auto-router cost tier, headroom, reported cost)
- [x] 1.2 `client.py` `get_llm` / `model_for` / `set_llm_factory`; `usage.py` `record_usage`
- [x] 1.3 Delete providers, registry, pricing, cassette provider; slim `LLMProvider`; drop `complete_json(on_response=)`

## 2. Callers

- [x] 2.1 Actions use `get_llm(model, context)`; never-fail actions degrade without a key
- [x] 2.2 `AgentLoop`, daemon, goals, CLI, commands, settings, API, goal form: tiers, no providers
- [x] 2.3 Built-in workflows (`model: low`, versions bumped), creator / variant prompts, scripts

## 3. Tests, deps, CI, docs

- [x] 3.1 Provider tests replaced by `test_openrouter.py` / `test_llm_client.py`; fakes via `set_llm_factory`; root conftest resets it
- [x] 3.2 Drop anthropic extra / SDK; deploy secrets; CI comments; e2e_live on OpenRouter
- [x] 3.3 `specs/openrouter-llm-design.md`, `specs/zebra-as-is.md`, AGENTS.md files, READMEs, `.env.example`
- [x] 3.4 Run lint + format (`uv run ruff check --fix . && uv run ruff format .`), full unit suite
- [x] 3.5 Prod: `site.env` `ZEBRA_LLM_MODEL=medium`, drop `ZEBRA_LLM_PROVIDER` / `OPENROUTER_ROUTING`; deploy + smoke green; a real goal completes
