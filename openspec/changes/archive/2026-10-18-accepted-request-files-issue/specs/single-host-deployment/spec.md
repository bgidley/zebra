## MODIFIED Requirements

### Requirement: Secrets sourced from GitLab CI variables
The deploy SHALL write `~/.config/zebra/prod.env` with mode 0600 from CI variables (`ORACLE_*`, `ANTHROPIC_API_KEY`, `KAGI_API_KEY`, `KIMI_*`, `OPENROUTER_*`, `ZEBRA_SMTP_*`, `ZEBRA_NOTIFY_WEBHOOK_URL`, `ZEBRA_GITLAB_TOKEN`), a host-persistent generated `DJANGO_SECRET_KEY`, and the non-secret `site.env`. Secrets MUST NOT be committed to the repository.

#### Scenario: Env file regenerated on deploy
- **WHEN** the deploy job runs with `ORACLE_DSN` in its environment
- **THEN** `prod.env` is rewritten atomically with mode 0600
- **AND** `DJANGO_SECRET_KEY` is unchanged from the previous deploy

#### Scenario: GitLab token reaches the app
- **WHEN** the deploy job runs with `ZEBRA_GITLAB_TOKEN` in its environment
- **THEN** `prod.env` contains `ZEBRA_GITLAB_TOKEN` and the `zebra-web` container can file issues with it
