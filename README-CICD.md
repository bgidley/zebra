# CI/CD

Zebra uses GitLab CI/CD with a **self-hosted runner on the Oracle VM** (`ssh opc`).
All pipeline jobs run on that VM — nothing executes on GitLab's shared runners.

GitLab project: https://gitlab.com/gidley/zebra

## Pipeline overview

Every push to `master` runs four stages in sequence:

```
lint  →  unit  →  e2e  →  deploy
```

| Stage | What runs | Backend | Time |
|---|---|---|---|
| **lint** | `ruff check .` + `ruff format --check .` | — | ~3s |
| **unit** | `pytest -m "not e2e"` (all packages) | SQLite | ~25s |
| **e2e** | `pytest zebra-agent-web/tests/e2e/ -m e2e` | Oracle E2E schema + cassette LLM | ~30s |
| **deploy** | `podman-compose up -d --build` | Oracle (prod) | ~15-70s |

The `e2e-live` job (real Anthropic API + Oracle DB) only runs on a scheduled pipeline
— it is **not** part of the push-triggered pipeline. See [Nightly schedule](#nightly-schedule).

## Architecture

```
Your laptop  ──git push──▶  gitlab.com/gidley/zebra
                                    │
                         (runner polls outbound)
                                    │
                             Oracle VM (opc)
                          ┌─────────────────────┐
                          │  gitlab-runner       │  shell executor, User=opc
                          │  ├── lint job        │
                          │  ├── unit job        │
                          │  ├── e2e job         │
                          │  └── deploy job      │
                          │       └── podman-compose up -d --build
                          │            └── zebra_web_1 (port 8000)
                          └─────────────────────┘
```

The runner polls GitLab outbound — no inbound port needed on the VM.

## Secrets

Sensitive values are stored as **masked, protected CI/CD variables** in
https://gitlab.com/gidley/zebra/-/settings/ci_cd → Variables:

| Variable | Used by |
|---|---|
| `ANTHROPIC_API_KEY` | e2e cassette recorder, e2e-live |
| `ORACLE_USERNAME` | e2e-live, deploy (via .env mount) |
| `ORACLE_PASSWORD` | e2e-live, deploy (via .env mount) |
| `ORACLE_DSN` | e2e-live, deploy (via .env mount) |

The runner injects these into every job's environment automatically.

**For the deploy and e2e-live jobs**, the Oracle credentials also need to exist
in `/home/opc/projects/zebra/.env` because `docker-compose.yml` mounts that
file into the container at `/app/.env`. The CI variables and the `.env` file
should be kept in sync.

## Stage details

### lint
```bash
uv sync --all-packages --frozen
uv run ruff check .
uv run ruff format --check .
```

### unit
```bash
uv sync --all-packages --frozen
uv run pytest -m "not e2e" --ignore=zebra-agent-web/tests/e2e_live
```

Runs against SQLite (no `ORACLE_DSN` injected). Covers all four packages.

### e2e
```bash
uv sync --all-packages --frozen
cp /home/opc/projects/zebra/.env .env
export ORACLE_DSN="$E2E_ORACLE_DSN" ORACLE_USERNAME="$E2E_ORACLE_USERNAME" ORACLE_PASSWORD="$E2E_ORACLE_PASSWORD"
uv run python zebra-agent-web/manage.py migrate --noinput --fake-initial
uv run python zebra-agent-web/manage.py flush --noinput
uv run pytest zebra-agent-web/tests/e2e/ -m e2e
```

Uses the dedicated `ZEBRA_TEST` Oracle E2E schema. `ANTHROPIC_API_KEY` is still
injected by the runner — the cassette recorder needs it when recording new LLM
interactions (`VCR_RECORD_MODE=once`).

If `E2E_ORACLE_DSN` is not set (e.g. local development without Oracle), the job
falls back to file-based SQLite with WAL mode (`--ds=zebra_agent_web.e2e_settings`).

LLM responses are replayed from cassettes in `zebra-agent-web/tests/e2e/cassettes/`.
To re-record, run with `VCR_RECORD_MODE=rewrite` (requires real API key).

### deploy
```bash
uv sync --all-packages --frozen
cp /home/opc/projects/zebra/.env .env   # needed for docker-compose .env mount
podman-compose up -d --build
podman-compose ps
```

Builds a fresh image from `Dockerfile`, replaces the running container.
The entrypoint (`docker/entrypoint.sh`) runs `manage.py migrate` then starts
Daphne on port 8000.

`resource_group: zebra-prod` ensures only one deploy runs at a time if multiple
merges land in quick succession.

## Nightly schedule

The `e2e-live` job runs the real-LLM suite against real Oracle. Configure it in
https://gitlab.com/gidley/zebra/-/pipeline_schedules:

- **Description**: Nightly E2E live
- **Interval**: `0 2 * * *` (02:00 UTC)
- **Target branch**: master

The job activates only when `$CI_PIPELINE_SOURCE == "schedule"`. The `deploy`
job is suppressed for scheduled pipelines (its rule requires `"push"`).

## Runner configuration

The runner is installed on the Oracle VM as a systemd service running as `User=opc`.

Key facts:
- **Executor**: shell (jobs run as `opc` directly — no container isolation)
- **Tag**: `opc-shell` (all jobs in `.gitlab-ci.yml` carry this tag)
- **Build dir**: `/home/opc/builds/FaiafcTHZ/0/gidley/zebra/` (stable per runner+project)
- **UV cache**: `/home/opc/.cache/uv` (shared across jobs — `uv sync` is fast after first run)
- **Config**: `/etc/gitlab-runner/config.toml`

To check runner status:
```bash
ssh opc 'systemctl status gitlab-runner'
ssh opc 'sudo gitlab-runner verify'
```

To re-bootstrap from scratch, see [`deploy/gitlab-runner-bootstrap.md`](deploy/gitlab-runner-bootstrap.md).

## Key files

| File | Purpose |
|---|---|
| `.gitlab-ci.yml` | Pipeline definition |
| `deploy/gitlab-runner-bootstrap.md` | One-shot runner install + registration |
| `Dockerfile` | Multi-stage image build (python:3.14-slim) |
| `docker-compose.yml` | Production container config (podman-compose compatible) |
| `docker/entrypoint.sh` | migrate → collectstatic → daphne |
| `zebra-agent-web/tests/e2e/cassettes/` | Recorded LLM interactions for e2e tests |
