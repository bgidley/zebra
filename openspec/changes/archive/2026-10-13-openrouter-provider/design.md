## Context

`KimiProvider` already shows the pattern: subclass `OpenAIProvider`, point the client at
another base URL, resolve model aliases. OpenRouter fits the same shape.

## Decisions

- **Subclass `OpenAIProvider`** — no new client code. Sends `X-Title: Zebra` for OpenRouter
  attribution.
- **Reported cost over price tables** — OpenRouter returns the billed USD cost in
  `usage.cost` for every call. Tracking it means no OpenRouter price table to maintain for
  hundreds of models. `TokenUsage.cost_usd` defaults to `None`, so other providers are
  unchanged.
- **Tier names map to Claude 5.5 on OpenRouter** — workflows say `model: haiku` etc.; under
  `openrouter` these keep their meaning.
- **Unknown names fall back to a default** (as Kimi does) rather than being sent raw, so a
  `claude-*` id written for Anthropic does not 400.

## Risks

- The provided key has no credits yet: paid models return 402 until credits are added; free
  `:free` models work.
- Context windows are only known for a few models; others default to 128K.
