Narrative design: [specs/work-zebra-mac-design.md](../../../../specs/work-zebra-mac-design.md), section WZ1.

Key decisions:
- Converse API (not InvokeModel / the Anthropic Bedrock SDK): one request shape for every Bedrock
  model, tool use included, and nothing vendor-specific outside `llm/bedrock.py`.
- A bearer API key is sent with an unsigned botocore client plus a `before-send` handler that sets
  `Authorization: Bearer`, so the key can come from a file that changes while Zebra runs.
- Cost from a local price table; an unknown model is charged the highest known rate (fail safe
  for the budget).
- Owner notice through a small `notify_owner` helper reusing the existing webhook / SMTP settings,
  once an hour per key, never raising.
