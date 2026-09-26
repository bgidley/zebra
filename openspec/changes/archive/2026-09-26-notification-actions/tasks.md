> Branch: `f65/notifications`. Reference `#65` in commits.

## 1. Implementation

- [x] 1.1 `zebra_tasks/notifications/smtp_email.py` — `NotifyEmailAction` (SMTP via `asyncio.to_thread`, env config)
- [x] 1.2 `zebra_tasks/notifications/webhook.py` — `NotifyWebhookAction` (httpx, recursive templates, scheme check)
- [x] 1.3 Register `notify_email` / `notify_webhook` entry points; `uv sync --all-packages`

## 2. Tests

- [x] 2.1 Email: send, default recipients, missing config, SMTP error without password leak, security modes
- [x] 2.2 Webhook: payload templating, default URL, non-2xx, network error, bad scheme
- [x] 2.3 Metadata: irreversible hint; lint + format

## 3. Docs & delivery

- [x] 3.1 `zebra-tasks/AGENTS.md`, `specs/zebra-as-is.md` catalogue + gap table
- [x] 3.2 Zebra feedback; push; green pipeline; merge; archive this change
