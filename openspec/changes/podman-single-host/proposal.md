## Why

The OKE cluster that ran Zebra (F108–F111) was lost: the agent deployed itself into the same cluster it was managing, a deploy severed connectivity, and the cluster had to be deleted. Prod is down and CI has no runner. Zebra moves back to the single OCI A1 instance the agent runs on, deploying directly to rootless Podman — with explicit guards so a deploy can never take down the host's control plane again. Closes #117.

## What Changes

- Prod runs as two rootless Podman **Quadlet** units on one host: `zebra-web` (Daphne, loopback only, health-gated) and exactly one `zebra-daemon`.
- New `scripts/deploy-podman.sh`: build `localhost/zebra-web:<sha>` locally (no registry), health-gated promote with automatic rollback, image pruning.
- Secrets flow from GitLab CI variables into a 0600 env file on each deploy; non-secret settings live in `site.env`.
- New idempotent `deploy/podman/bootstrap-host.sh` (uv, GitLab shell runner as `opc`, linger, cloudflared, root FS growth).
- Public access at `zebra.gidley.co.uk` via Cloudflare Tunnel behind Cloudflare Access, replacing Tailscale; passkeys re-registered for the new RP ID.
- `.gitlab-ci.yml`: all jobs tagged `opc-shell`; `oke_*` jobs and `OKE_ENABLED` gating removed. **BREAKING** for the pipeline topology.
- Remove `deploy/oke/`, `docker/claude/`, `docker-compose.yml`, the old runner doc and the OKE design spec.

## Capabilities

### New Capabilities
- `single-host-deployment`: prod web + single daemon under rootless Podman on one host, health-gated deploy/rollback, CI via a host shell runner, and blast-radius limits that protect the host.

### Modified Capabilities
<!-- None — the OKE container-deployment capability was never synced to openspec/specs. -->

## Non-goals

- HA, multiple hosts, or an image registry.
- Pre-deploy smoke against a separate schema (smoke runs post-deploy, as before OKE).
- A claude-code sandbox container — the agent runs directly on the host.
- Any change to the Oracle ADB, app code, or UX.

## Impact

- New: `deploy/podman/**`, `scripts/deploy-podman.sh`, `specs/podman-single-host-design.md`.
- Changed: `.gitlab-ci.yml`, `README-CICD.md`, `specs/zebra-as-is.md` §7, `AGENTS.md`.
- Removed: `deploy/oke/**`, `docker/claude/`, `docker-compose.yml`, `deploy/gitlab-runner-bootstrap.md`, `specs/oke-migration-design.md`.
- External: GitLab project runner `coding-agent-podman` (tag `opc-shell`); stale runners to delete.
