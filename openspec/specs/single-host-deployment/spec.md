# single-host-deployment Specification

## Purpose
How Zebra prod and CI run on a single host under rootless Podman: the web + single-daemon units, health-gated deploy and rollback, secrets flow, blast-radius limits, and the host shell runner.

## Requirements

### Requirement: Prod runs as rootless Podman Quadlet units on one host
Zebra prod SHALL run on a single host as two rootless Podman Quadlet units from the same locally built image: `zebra-web` (Daphne) and `zebra-daemon` (`manage.py run_daemon`). The web unit MUST set `ZEBRA_DAEMON_AUTO_START=0` and MUST publish only on `127.0.0.1:8000`.

#### Scenario: Both units running after deploy
- **WHEN** a deploy completes successfully
- **THEN** `zebra-web` is running and healthy and `zebra-daemon` is running
- **AND** port 8000 is bound to loopback only

#### Scenario: Units survive reboot without a login session
- **WHEN** the host reboots
- **THEN** both units start automatically under the `opc` user manager (linger enabled)

### Requirement: Exactly one budget daemon
At most one `zebra-daemon` container SHALL run at any time. The deploy MUST stop the daemon before swapping images and MUST start it only after the new web container is healthy.

#### Scenario: No daemon overlap during deploy
- **WHEN** a deploy promotes a new image
- **THEN** the old daemon is stopped before `:prod` is retagged
- **AND** the new daemon starts only after `zebra-web` passes its health check

### Requirement: Health-gated deploy with automatic rollback
`scripts/deploy-podman.sh <tag>` SHALL build `localhost/zebra-web:<tag>`, retag the current `:prod` as `:previous`, promote `:<tag>` to `:prod` and restart web, blocking until `/api/health/` passes. If web does not become healthy, the script MUST re-promote the previous image and exit non-zero. `--rollback` SHALL re-promote `:previous`.

#### Scenario: Healthy deploy
- **WHEN** the new image starts and `/api/health/` returns 200
- **THEN** the script exits 0 and prunes to the newest `KEEP_IMAGES` builds

#### Scenario: Unhealthy deploy rolls back
- **WHEN** the new web container fails its health check
- **THEN** the previous image is re-promoted and restarted
- **AND** the script exits non-zero, failing the pipeline

### Requirement: Secrets sourced from GitLab CI variables
The deploy SHALL write `~/.config/zebra/prod.env` with mode 0600 from CI variables (`ORACLE_*`, `ANTHROPIC_API_KEY`, `KAGI_API_KEY`, `KIMI_*`, `ZEBRA_SMTP_*`, `ZEBRA_NOTIFY_WEBHOOK_URL`), a host-persistent generated `DJANGO_SECRET_KEY`, and the non-secret `site.env`. Secrets MUST NOT be committed to the repository.

#### Scenario: Env file regenerated on deploy
- **WHEN** the deploy job runs with `ORACLE_DSN` in its environment
- **THEN** `prod.env` is rewritten atomically with mode 0600
- **AND** `DJANGO_SECRET_KEY` is unchanged from the previous deploy

### Requirement: Deploy blast radius is limited to the app units
The deploy SHALL only start, stop or restart the `zebra-web` and `zebra-daemon` user units. It MUST NOT restart the GitLab runner, sshd, cloudflared or host networking, and app containers MUST be memory-capped.

#### Scenario: Failed deploy leaves control plane intact
- **WHEN** a deploy fails at any step
- **THEN** the GitLab runner, SSH and the Cloudflare Tunnel remain up

### Requirement: CI runs on a host shell runner
All pipeline jobs SHALL run on a GitLab shell runner on the prod host, executing as `opc`, tagged `opc-shell`, with `concurrent = 1`. `deploy/podman/bootstrap-host.sh` SHALL idempotently install and register it.

#### Scenario: Pipeline picks up on the host runner
- **WHEN** a commit is pushed
- **THEN** its jobs run on the `opc-shell` runner
