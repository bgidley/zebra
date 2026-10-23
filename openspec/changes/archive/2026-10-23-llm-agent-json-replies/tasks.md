## 1. llm_agent

- [x] 1.1 `agent.py`: JSON final answers parsed with `parse_llm_json`; one tool-less retry (JSON-only note, or 2× `max_tokens` + brief note when truncated); fail with `describe_failure` when still unusable
- [x] 1.2 Unit tests: junk → retry succeeds; junk twice → fails, no `output_key`; truncated retry gets 2× tokens; text unchanged

## 2. Outcome Review

- [x] 2.1 Workflow tests: junk reconsideration twice fails the review; valid retry is compared

## 3. Docs and checks

- [x] 3.1 `zebra-tasks/AGENTS.md` `llm_agent` section; `specs/zebra-as-is.md`
- [x] 3.2 ruff, unit tests, `openspec validate llm-agent-json-replies --strict`
