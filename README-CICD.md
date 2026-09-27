# CI/CD

Zebra uses GitLab CI/CD with a **self-hosted shell runner on the single prod host** — the
OCI A1 instance `coding-agent` (Oracle Linux 9, 2 OCPU / 10 GB). The same host runs prod
under **rootless Podman** (systemd Quadlet units). Nothing runs on GitLab's shared runners.

GitLab project: https://gitlab.com/gidley/zebra

> History: prod ran on a VM with podman-compose, then on OKE (F108–F111). The OKE cluster
> was lost in Sept 2026 — a deploy severed the cluster the agent was managing — and was
> deleted. F117 moved back to one host. Design: [specs/podman-single-host-design.md](specs/podman-single-host-design.md).

## Pipeline

```
lint  →  test  →  e2e  →  deploy  →  smoke
```

| Stage | Job | What runs | When |
|---|---|---|---|
| lint | `lint` | `ruff check` + `ruff format --check` | every push |
| test | `unit` | `pytest -m "not e2e and not smoke"` on SQLite | every push |
| e2e | `e2e` | `pytest tests/e2e -m e2e` — ephemeral Oracle schema, or SQLite fallback | every push |
| e2e | `e2e-live` | real-LLM tests against prod Oracle | schedules only |
| deploy | `deploy` | `scripts/deploy-podman.sh $SHA` | `master` push |
| smoke | `smoke` | `pytest tests/smoke -m smoke` against `http://localhost:8000` | after deploy |

`deploy` uses `resource_group: zebra-prod`, so deploys never overlap.

## Architecture

```
laptop ──git push──▶ gitlab.com/gidley/zebra
                           │ (runner polls outbound)
                           ▼
 coding-agent (OCI A1) ─────────────────────────────────────────────
   gitlab-runner.service   shell executor, runs jobs as opc, concurrent=1
   │ deploy job: podman build → localhost/zebra-web:<sha> (no registry)
   ▼
   systemd --user (linger)          ~/.config/containers/systemd/
     zebra-web.service     Daphne, 127.0.0.1:8000, health-gated, 1.5 GB cap
     zebra-daemon.service  manage.py run_daemon — exactly one, 768 MB cap
   cloudflared.service     Cloudflare Tunnel (outbound only) → 127.0.0.1:8000
                           https://zebra.gidley.co.uk, behind Cloudflare Access
   Oracle ADB "Zebra"      remote, TLS DSN, no wallet
```

**Blast radius rule**: the deploy only ever restarts the `zebra-web` / `zebra-daemon` user
units. It never touches the runner, sshd, cloudflared or host networking, and containers are
memory-capped so a runaway app cannot OOM the host the agent and runner live on.

## Deploy (`scripts/deploy-podman.sh`)

1. Writes `~/.config/zebra/prod.env` (0600) from the job's CI variables
   (`ORACLE_*`, `ANTHROPIC_API_KEY`, `KAGI_API_KEY`, `KIMI_*`, `ZEBRA_SMTP_*`,
   `ZEBRA_NOTIFY_WEBHOOK_URL`), a persistent generated
   `DJANGO_SECRET_KEY`, and the non-secret `~/.config/zebra/site.env`.
2. `podman build -t localhost/zebra-web:$SHA .`
3. Installs `deploy/podman/quadlet/*.container` and reloads systemd.
4. Stops the daemon, tags the current `:prod` as `:previous`, tags the new image `:prod`.
5. Restarts `zebra-web` — blocks until the container health check passes (web runs migrations).
6. Starts `zebra-daemon`, provisions the `smoke` user, prunes to the newest 5 images.

If web never becomes healthy the previous image is re-promoted and the job fails.

Manual operations (on the host, as `opc`):

```bash
systemctl --user status zebra-web zebra-daemon
podman logs -f zebra-web            # or: journalctl --user -u zebra-web -f
podman exec zebra-web tail -f zebra-agent-web/tmp/zebra.log   # rotating file logs (volume zebra-logs)
scripts/deploy-podman.sh --rollback # re-promote :previous
touch ~/.config/zebra/hold-daemon   # future deploys leave the daemon stopped
rm ~/.config/zebra/hold-daemon && systemctl --user start zebra-daemon   # resume
podman exec zebra-web python zebra-agent-web/manage.py kill_switch --status
```

## Secrets

GitLab CI/CD variables (https://gitlab.com/gidley/zebra/-/settings/ci_cd) are the single
source of truth; the host copy is regenerated on every deploy.

| Variable | Used by |
|---|---|
| `ORACLE_DSN` / `ORACLE_USERNAME` / `ORACLE_PASSWORD` | prod containers, `e2e-live` |
| `ANTHROPIC_API_KEY`, `KAGI_API_KEY` | prod containers, e2e cassette recording |
| `KIMI_API_KEY` (+ optional `KIMI_BASE_URL`) | prod containers — `--model kimi` (default for `scripts/zebra-feedback.sh`) |
| `ZEBRA_SMTP_USERNAME` / `ZEBRA_SMTP_PASSWORD` | prod containers — `notify_email` via OCI Email Delivery (an OCI user SMTP credential; host/sender live in `site.env`) |
| `ZEBRA_NOTIFY_WEBHOOK_URL` (optional) | prod containers — default target for `notify_webhook` |
| `SMOKE_PASSWORD` | deploy (creates `smoke` user), `smoke` |
| `E2E_PROVISIONER_DSN` / `_USERNAME` / `_PASSWORD` | `e2e` ephemeral Oracle schema (SQLite fallback when unset) |

`DJANGO_SECRET_KEY` is generated once on the host (`~/.config/zebra/django_secret_key`).

## Rebuilding the host

```bash
git clone https://gitlab.com/gidley/zebra.git ~/code/zebra && cd ~/code/zebra
# Create a project runner (tag opc-shell) and register it in one go:
RUNNER_TOKEN=$(glab api -X POST user/runners -f runner_type=project_type \
  -f project_id=77537461 -f tag_list=opc-shell -F run_untagged=false | jq -r .token) \
  deploy/podman/bootstrap-host.sh
cloudflared tunnel login                     # interactive: authorise the gidley.co.uk zone
deploy/podman/setup-tunnel.sh zebra.gidley.co.uk  # named tunnel "zebra" + DNS + system service
```

Then re-run the latest `master` pipeline (or push) to deploy.

## Key files

| File | Purpose |
|---|---|
| `.gitlab-ci.yml` | Pipeline definition |
| `Dockerfile`, `docker/entrypoint.sh` | Image build; entrypoint migrates + starts Daphne |
| `deploy/podman/bootstrap-host.sh` | Idempotent host setup (uv, runner, linger, cloudflared, growfs) |
| `deploy/podman/setup-tunnel.sh` | Cloudflare Tunnel: hostname → `127.0.0.1:8000`, system service |
| `deploy/podman/quadlet/` | `zebra-web` / `zebra-daemon` Quadlet units |
| `deploy/podman/site.env.example` | Non-secret prod settings template |
| `scripts/deploy-podman.sh` | Build + health-gated promote + rollback |
| `scripts/e2e_oracle_schema.py` | Ephemeral E2E Oracle schema provisioner |
| `zebra-agent-web/tests/smoke/` | Post-deploy smoke tests |
| `zebra-agent-web/tests/e2e_live/` | Real-LLM live tests (scheduled) |
