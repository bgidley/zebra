## Why

Zebra runs on a single Always-Free VM where prod, smoke tests, and Claude Code share one host with no isolation: smoke tests run against the live prod instance (writing to the prod Oracle schema and spending prod budget), and the disk fills from repeated image builds. Moving to Oracle Kubernetes Engine (OKE) gives each concern its own isolated, reproducible, IaC-defined home. Closes #108.

## What Changes

- Run Zebra's workloads on an OKE cluster with images in OCIR, defined entirely as Infrastructure-as-Code under `deploy/oke/` (Terraform + kustomize + scripts + onboarding doc) and `docker/claude/Dockerfile`.
- Split the prod app into two Kubernetes Deployments: `zebra-web` (Daphne) and `zebra-daemon` (`manage.py run_daemon`), replacing the in-process `DaemonStarterMiddleware` start. **BREAKING** for the deployment topology (web sets `ZEBRA_DAEMON_AUTO_START=0`).
- Add a `claude-code` sandbox pod (autonomous agent + dev), repo on a PVC.
- Replace "smoke tests hit live prod" with an **ephemeral smoke namespace** against a dedicated Oracle smoke schema, torn down after each run.
- Adopt a **build-once → smoke-validate → promote** release flow: the prod image is the byte-identical `:sha` that passed smoke (`kubectl set image`, no rebuild).
- Move CI into the cluster (GitLab Runner, Kubernetes executor); pipeline becomes `lint → test → e2e → build → smoke → deploy`.

## Capabilities

### New Capabilities
- `container-deployment`: Zebra's runtime topology on OKE — prod web/daemon split, claude-code sandbox, OCIR images, isolated smoke instance, and free-tier-shaped reproducible infrastructure.
- `release-promotion`: build the image once, validate it in an isolated ephemeral smoke environment, then promote the exact same image to prod.

### Modified Capabilities
<!-- None — no existing capability's requirements change. -->

## Impact

- New: `deploy/oke/**` (Terraform, kustomize, scripts, docs), `docker/claude/Dockerfile`, `specs/oke-migration-design.md`.
- Changed: `.gitlab-ci.yml` (later increment); budget daemon runs as its own process.
- External: new dedicated Oracle **smoke** schema; OCI tenancy (OKE Basic, OCIR, 10 Mbps LB) — free-tier except a ~$5 parallel-run week.
- Non-goals: no change to the Oracle ADB itself, the workflow engine, app domain code, or the web UX; no multi-node/HA; no autoscaling.
