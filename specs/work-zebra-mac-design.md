# Work Zebra on a corporate Mac (#334)

A *work Zebra* is the owner's own Zebra for work, on the corporate Mac: a related instance
(sphere `work`, `observed`) of the home Zebra. Only workflows cross, over the private sync relay.
It runs sandboxed in Apple `container`, uses AWS Bedrock for LLM calls and Postgres + pgvector for
storage. OCI prod is unchanged; everything is opt-in by config. The decisions, topology and ticket
order are on the tracking issue #334. This file holds the technical detail, one section per ticket.

| Ticket | Issue | Status |
|---|---|---|
| WZ1 Bedrock LLM provider | #335 | Implemented, unit-tested; live check in WZ5 |
| WZ2 sandbox on Apple container | #336 | Pending |
| WZ3 egress allowlist proxy | #337 | Pending |
| WZ4 sync relay through CONNECT | #338 | Pending |
| WZ5 pair the work Mac, live E2E | #339 | Pending |
| WZ6 host-side Bedrock token bridge | #340 | Pending |

## WZ1: Bedrock LLM provider (#335)

### Goal and scope
Zebra can use AWS Bedrock instead of OpenRouter, chosen by `ZEBRA_LLM_PROVIDER`, with tiers, tool
use, cost tracking, the daily budget and cost caps working as they do on OpenRouter. Not in scope:
streaming, prompt caching, Bedrock guardrails, embeddings, and running against live Bedrock (WZ5).

### Data model
No new tables or migrations. `TokenUsage.cost_usd` is computed from tokens instead of reported, so
`__total_cost__`, `__token_history__` and the spend ledger (`LLMSpendModel`, model = the Bedrock
model ID) are filled as before.

### Interfaces
- `zebra_tasks/llm/bedrock.py`: `BedrockLLM(LLMProvider)` on the Converse API (boto3
  `bedrock-runtime`, called in `asyncio.to_thread`).
  - `Message` → Converse: system messages become `system` text blocks; tool results become
    `toolResult` blocks in a user turn; assistant tool calls become `toolUse` blocks; consecutive
    same-role turns are merged (Converse wants them alternating). With no tools on the request,
    tool history is written as text (Converse refuses tool blocks without a `toolConfig`; the
    `llm_agent` tool-budget answer does this).
  - `ToolDefinition` → `toolConfig.tools[].toolSpec` with `inputSchema.json`, `toolChoice: auto`.
  - Response: `text` blocks joined, `toolUse` → `ToolCall`, `reasoningContent` dropped;
    `finish_reason` = Converse `stopReason` (`max_tokens` is already read as truncation).
  - `maxTokens` = requested + 4096 reasoning headroom (as #204). `temperature` is left out for
    models that refuse sampling parameters (Fable, Mythos, Opus 5+, Sonnet 5+, Haiku 5+, Opus 4.7/4.8).
- `zebra_tasks/llm/models.py`: `llm_provider()`; `normalize_model()` accepts a Bedrock ID
  (`[geo.]vendor.model[:n]`) or ARN on Bedrock; an OpenRouter `vendor/model` slug maps to its tier
  with a warning (haiku/kimi → low, sonnet → medium, opus → high, else medium). On OpenRouter a
  Bedrock ID is read as its tier the same way.
- `zebra_tasks/llm/client.py`: `get_llm()` builds `BedrockLLM` when the provider is `bedrock`;
  `set_llm_factory` still wins.
- `zebra_tasks/llm/base.py`: `LLMProviderAuthError`.
- `zebra_tasks/notifications/owner.py`: `notify_owner(key, subject, body)`.

### Credentials and the token file (for WZ6)
Without `ZEBRA_BEDROCK_TOKEN_FILE` the standard boto3 chain is used (`AWS_PROFILE`, env keys, SSO,
`AWS_BEARER_TOKEN_BEDROCK`). With it, the file is read on every call when its mtime changes (a
client per file version is cached), in one of three formats:

1. **Bare Bedrock API key**: the whole file, whitespace stripped. Sent as
   `Authorization: Bearer <key>` (the client is unsigned, no SigV4).
2. **API key with expiry** (preferred for WZ6 `--mode key`):
   `{"token": "<bedrock api key>", "expires_at": "2026-11-26T18:00:00Z"}`.
3. **Session credentials** (WZ6 `--mode session`): exactly what
   `aws configure export-credentials --profile X --format process` prints:
   `{"Version": 1, "AccessKeyId": "…", "SecretAccessKey": "…", "SessionToken": "…",
   "Expiration": "2026-11-26T18:00:00+00:00"}`. Signed with SigV4.

The writer should replace the file atomically (write a temp file, then rename). An expiry in the
past fails the call before it is made. A missing, empty or unparseable file, an expired expiry, a
botocore `NoCredentialsError` / `CredentialRetrievalError` / `TokenRetrievalError` / `SSOError`,
or a `ClientError` with an auth code (`ExpiredToken*`, `UnrecognizedClientException`,
`InvalidSignatureException`, HTTP 401, or `AccessDeniedException` mentioning a token or expiry)
raises `LLMProviderAuthError`:

> AWS session expired — run `aws sso login --profile <ZEBRA_BEDROCK_SSO_PROFILE or AWS_PROFILE>` (detail)

`llm_call` / `llm_agent` fail the task with it, so the goal fails with that message. The provider
then calls `notify_owner("bedrock-auth", …)`: logged at ERROR, POSTed as `{"subject", "body"}` to
`ZEBRA_NOTIFY_WEBHOOK_URL` and emailed to `ZEBRA_NOTIFY_EMAIL_TO` (via `ZEBRA_SMTP_*`) when set, at
most once an hour.

### Cost
`DEFAULT_PRICES` in `bedrock.py` maps model-ID fragments to USD per 1M input / output tokens
(Anthropic list prices; the longest matching fragment wins). `ZEBRA_BEDROCK_PRICES` (JSON
`{"<fragment>": {"input": x, "output": y}}` or `[x, y]`) adds or replaces entries; set it to the
account's real rates (regional profiles cost more than `global.`). A model with no entry is charged
the highest rate in the table, with a warning, so it never counts as free.

### Timeouts and retries
botocore `Config(read_timeout=llm_request_timeout(), connect_timeout=10,
retries={"total_max_attempts": LLM_MAX_RETRIES + 1, "mode": "standard"})`: 180 s per attempt,
3 attempts (#183). Standard mode retries throttling and 5xx; after that the `ClientError` fails the
task. A read / connect timeout is raised as `TimeoutError`. botocore honours `HTTPS_PROXY` /
`NO_PROXY`, so calls go through the WZ3 egress proxy (`bedrock-runtime.<region>.amazonaws.com` is
on its allowlist; `test_egress_proxy_clients.py` checks Bedrock and the owner webhook).

### Configuration
`ZEBRA_LLM_PROVIDER` (`openrouter` default / `bedrock`), `AWS_REGION` (default `us-east-1`),
`ZEBRA_BEDROCK_MODEL_LOW|MEDIUM|HIGH|MAX` (defaults `global.anthropic.claude-haiku-5-5`,
`…sonnet-5-5`, `…opus-5-5`, `…opus-5-5`), `ZEBRA_BEDROCK_PRICES`, `ZEBRA_BEDROCK_TOKEN_FILE`,
`ZEBRA_BEDROCK_SSO_PROFILE`. Dependency: `boto3` (pure Python, arm64 / macOS fine).

### Open questions and risks
- Which models / inference profiles (`global.` / `us.` / `eu.`) the corporate account enables, and
  their prices: set the tier map and `ZEBRA_BEDROCK_PRICES` in WZ5.
- Thinking models on Converse: their `reasoningContent` is not replayed in a multi-turn tool loop.
  If Bedrock insists on it, `Message` will need to carry the blocks (check live in WZ5).
- Only unit-tested with botocore `Stubber`; the live call and `aws sso logout` check are in WZ5.
