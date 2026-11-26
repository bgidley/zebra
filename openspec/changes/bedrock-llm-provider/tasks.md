## 1. Implementation
- [x] 1.1 `BedrockLLM` (Converse mapping, tool use, temperature rules, headroom)
- [x] 1.2 Provider selection in `get_llm`, `normalize_model` Bedrock IDs and slug fallback
- [x] 1.3 Tier map, price table + `ZEBRA_BEDROCK_PRICES`, botocore timeout / retries
- [x] 1.4 Credentials: boto3 chain, token file (three formats, mtime reload), `LLMProviderAuthError`
- [x] 1.5 `notify_owner` helper and the auth-failure notice
- [x] 1.6 `boto3` dependency

## 2. Tests
- [x] 2.1 `zebra-tasks/tests/test_llm_bedrock.py` (Stubber: text, JSON, tools, cost, timeout, throttling, expired token, token file, tiers, provider, slugs)

## 3. Docs
- [x] 3.1 AGENTS.md tiers + settings, zebra-tasks AGENTS, as-is, `specs/work-zebra-mac-design.md`, specs index
