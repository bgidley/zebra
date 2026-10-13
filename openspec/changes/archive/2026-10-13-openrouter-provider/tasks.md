## 1. Provider

- [x] 1.1 `OpenRouterProvider` in `zebra_tasks/llm/providers/openrouter.py`, registered as `openrouter`
- [x] 1.2 `OPENROUTER_TIER_MODELS` in `llm/models.py`; tier, `claude-*` id, slug and default resolution
- [x] 1.3 `TokenUsage.cost_usd` filled from `usage.cost`

## 2. Cost tracking

- [x] 2.1 `pricing.usage_cost()`; used by `llm/action.py`, `agent/curator.py`, `knowledge/review.py`

## 3. Entry points & deploy

- [x] 3.1 `--model openrouter` in `zebra goal` and `run_goal`
- [x] 3.2 `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` in `deploy-podman.sh` `SECRET_VARS`
- [x] 3.3 `OPENROUTER_API_KEY` set as a masked GitLab CI variable

## 4. Tests & docs

- [x] 4.1 Unit tests for resolution, missing key, reported cost, `usage_cost`
- [x] 4.2 README-CICD, `.env.example`, zebra-tasks AGENTS.md, `specs/zebra-as-is.md`
- [x] 4.3 Zebra feedback
