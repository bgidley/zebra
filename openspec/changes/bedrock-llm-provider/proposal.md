## Why

The work Zebra (#334) runs on a corporate Mac where LLM calls must go to AWS Bedrock with the
owner's SSO account, not OpenRouter (#335, WZ1).

## What Changes

- `BedrockLLM` on the Bedrock Converse API (boto3): messages, system prompt, temperature,
  max tokens, tool use.
- `ZEBRA_LLM_PROVIDER=openrouter|bedrock` (default `openrouter`) selects the provider in `get_llm()`.
- Tier map `ZEBRA_BEDROCK_MODEL_<TIER>` + `AWS_REGION`; `normalize_model` accepts Bedrock IDs on
  Bedrock and reads OpenRouter slugs as their tier.
- Token-priced cost (`ZEBRA_BEDROCK_PRICES` override) so budget and cost caps keep working.
- Credentials: boto3 chain or `ZEBRA_BEDROCK_TOKEN_FILE` (re-read on change); expired credentials
  raise `LLMProviderAuthError` with an `aws sso login` message and notify the owner.
- `boto3` dependency for zebra-tasks.

## Non-goals

Streaming, prompt caching, Bedrock guardrails, live Bedrock verification (WZ5, #339), the host
token bridge (WZ6, #340).

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | With `ZEBRA_LLM_PROVIDER=bedrock`, text, JSON and tool-use calls go through `BedrockLLM` on the Converse API (tier → `ZEBRA_BEDROCK_MODEL_<TIER>`; exact IDs such as `global.anthropic.claude-opus-5-5`, `amazon.nova-pro-v1:0` and inference-profile ARNs sent as given; OpenRouter slugs read as their tier) and each call's token-priced cost lands in `__total_cost__` and the spend ledger (model = Bedrock ID), which the daily budget and `__cost_cap_usd__` already read | botocore Stubber unit tests in `zebra-tasks/tests/test_llm_bedrock.py` (request bodies, tool calls, usage → `cost_usd`, `__total_cost__`, ledger row, tier map, `ZEBRA_BEDROCK_PRICES`, provider selection). Live Bedrock call: WZ5 (#339) on the Mac, by the owner |
| O2 | Expired or missing AWS credentials fail the call, and so the goal, with the literal message "AWS session expired — run `aws sso login --profile <profile>`" and POST `{"subject", "body"}` to `ZEBRA_NOTIFY_WEBHOOK_URL` / email `ZEBRA_NOTIFY_EMAIL_TO` (at most once an hour); a stalled call fails after `ZEBRA_LLM_TIMEOUT_SECONDS` (180 s) x 3 attempts and throttling / 5xx are retried twice then fail as a normal error, never a hang; a rewritten token file is used without a restart | unit tests: Stubber `ExpiredTokenException` → `LLMProviderAuthError` with that string, `llm_call` task error, webhook payload + rate limit, botocore `Config` values, `ThrottlingException` not an auth error, token-file mtime reload. Manual `aws sso logout` check: WZ5 (#339), by the owner |
| O3 | Default behaviour (OpenRouter) is unchanged | existing LLM tests unchanged and green; master pipeline `deploy` and `smoke` jobs green and prod `short_hash` = merge commit |
