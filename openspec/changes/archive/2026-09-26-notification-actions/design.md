## Context

Task actions reach external services directly (see `kagi_search`, which reads `KAGI_API_KEY` from the environment). The engine is fully async, so blocking I/O must not run on the event loop.

## Decisions

- **SMTP via stdlib in a worker thread.** `smtplib` + `email.message.EmailMessage` inside `asyncio.to_thread`. Avoids adding `aiosmtplib` for one call per run.
- **Configuration by env var.** `ZEBRA_SMTP_HOST` (required), `ZEBRA_SMTP_PORT` (default 587), `ZEBRA_SMTP_SECURITY` = `starttls` (default) | `ssl` | `none`, `ZEBRA_SMTP_USERNAME` / `ZEBRA_SMTP_PASSWORD` (login only if username set), `ZEBRA_SMTP_FROM` (defaults to username). Default recipients `ZEBRA_NOTIFY_EMAIL_TO` (comma-separated). Default webhook `ZEBRA_NOTIFY_WEBHOOK_URL`.
- **Secrets never echoed.** Outputs and error messages omit the SMTP password and the webhook URL's path/query; only the webhook host is reported.
- **Templates resolved recursively** in webhook payloads (strings inside dicts/lists) so a YAML payload like `{text: "{{summary}}"}` works.
- **Webhook scheme allow-list**: only `http`/`https`. Non-2xx responses fail the task.
- **Irreversible.** Both actions set `reversibility_hint = "always_irreversible"`, so trust gates treat them as side-effecting.

## Risks

- A workflow in a loop could spam a mailbox; rate limiting is left to F30.
- SSRF via webhook URL: the URL comes from workflow definitions (authored by the user or the agent's workflow creator). Ethics/trust gates apply at the workflow level; a host allow-list is deferred.
