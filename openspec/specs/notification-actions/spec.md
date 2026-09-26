### Requirement: Email notification action
The `notify_email` action SHALL send an email over SMTP using server settings from `ZEBRA_SMTP_*` environment variables, with `to`, `subject` and `body` resolved from `{{templates}}`. Recipients SHALL default to `ZEBRA_NOTIFY_EMAIL_TO` when `to` is not given. On success it SHALL output the recipients and subject.

#### Scenario: Email sent
- **WHEN** SMTP is configured and the task has `to`, `subject` and `body`
- **THEN** one message is sent to the resolved recipients with the resolved subject and body, and the task succeeds

#### Scenario: Default recipients
- **WHEN** the task has no `to` and `ZEBRA_NOTIFY_EMAIL_TO` is set
- **THEN** the message is sent to the addresses in `ZEBRA_NOTIFY_EMAIL_TO`

#### Scenario: Not configured
- **WHEN** `ZEBRA_SMTP_HOST` is unset, or no recipient can be determined
- **THEN** the task fails with a configuration error and nothing is sent

#### Scenario: Delivery error
- **WHEN** the SMTP server refuses the connection or the message
- **THEN** the task fails with the error and the SMTP password does not appear in the error

### Requirement: Webhook notification action
The `notify_webhook` action SHALL send a JSON `payload` (templates resolved recursively) or a raw `body` to `url`, defaulting to `ZEBRA_NOTIFY_WEBHOOK_URL`. Only `http` and `https` URLs SHALL be accepted. A non-2xx response SHALL fail the task.

#### Scenario: Webhook delivered
- **WHEN** the endpoint returns a 2xx status
- **THEN** the task succeeds with the status code, and the payload sent has its templates resolved

#### Scenario: Endpoint rejects
- **WHEN** the endpoint returns a non-2xx status or is unreachable
- **THEN** the task fails with the status or network error

#### Scenario: Bad URL
- **WHEN** no URL is configured or the URL scheme is not http/https
- **THEN** the task fails and no request is made

### Requirement: Notifications are declared irreversible
Both notification actions SHALL declare `reversibility_hint = "always_irreversible"` so trust gates treat sending as a side effect that cannot be undone.

#### Scenario: Metadata
- **WHEN** the action metadata is inspected
- **THEN** `reversibility_hint` is `always_irreversible` for `notify_email` and `notify_webhook`
