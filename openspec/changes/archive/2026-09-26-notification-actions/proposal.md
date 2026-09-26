## Why

Zebra only acts when someone opens the web form, and it has no way to tell anyone when it has finished or found something. In the 30 days to 2026-09-26 prod saw no real day-to-day goals. Outbound notifications are the missing channel — the prerequisite for a scheduled research digest (F47), the notification system (F30) and agent-proposed goals (F29). Closes #65.

## What Changes

- New `notify_email` task action: sends a plain-text (optionally HTML) email over SMTP. Server settings come from `ZEBRA_SMTP_*` env vars; recipients default to `ZEBRA_NOTIFY_EMAIL_TO`.
- New `notify_webhook` task action: sends a JSON payload (or raw body) by HTTP POST/PUT to a URL, which defaults to `ZEBRA_NOTIFY_WEBHOOK_URL` so secret-bearing URLs (Slack, Discord, ntfy) stay out of workflow YAML.
- Both resolve `{{templates}}` in their content, declare `reversibility_hint = "always_irreversible"`, and fail the task (never crash) on misconfiguration or delivery errors.

## Capabilities

### New Capabilities
- `notification-actions`: outbound email and webhook task actions.

### Modified Capabilities
<!-- None -->

## Non-goals

- Channel routing, quiet hours, delivery retries/queueing (F30).
- Inbound webhooks / trigger bus (REQ-PRIN-009).
- Per-user SMTP credentials via the credential store (store is not injected into engine extras in prod yet; env vars match the `kagi_search` precedent).

## Impact

- New package `zebra-tasks/zebra_tasks/notifications/`, two entry points, tests in `zebra-tasks/tests/notifications/`.
- No new dependencies (stdlib `smtplib`/`email` run via `asyncio.to_thread`; `httpx` already present).
- Prod needs `ZEBRA_SMTP_*` secrets wired before email works; until then the action fails cleanly with a configuration error.
