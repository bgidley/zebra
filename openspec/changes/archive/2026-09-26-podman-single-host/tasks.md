> Branch: `f117/podman-single-host` (per fN/short-description). Reference `#117` in commits.

## 1. Host

- [x] 1.1 `deploy/podman/bootstrap-host.sh`: growfs, uv, gitlab-runner as `opc` (concurrent 1), linger, cloudflared, config dirs
- [x] 1.2 Run bootstrap on `coding-agent`; register runner `coding-agent-podman` (tag `opc-shell`) via API
- [x] 1.3 Remove Tailscale from host; `deploy/podman/setup-tunnel.sh`
- [x] 1.4 `cloudflared tunnel login` (user) + `setup-tunnel.sh zebra.gidley.co.uk`
- [x] 1.5 Cloudflare Access application on `zebra.gidley.co.uk` (owner only)

## 2. Deploy

- [x] 2.1 Quadlet units `zebra-web` (health-gated, loopback, mem cap) and `zebra-daemon` (single, after web)
- [x] 2.2 `scripts/deploy-podman.sh`: env from CI vars, build, promote, rollback, prune, smoke user
- [x] 2.3 `site.env.example` (WebAuthn/CSRF origin `https://zebra.gidley.co.uk`)
- [x] 2.4 Test: dry-run deploy on SQLite — healthy promote, daemon ordering, `--rollback`; torn down

## 3. Pipeline & cleanup

- [x] 3.1 `.gitlab-ci.yml`: tag `opc-shell`, drop `oke_*` / `OKE_ENABLED`, deploy via script, e2e-live via CI vars
- [x] 3.2 Remove `deploy/oke/`, `docker/claude/`, `docker-compose.yml`, old runner doc, OKE design spec
- [x] 3.3 Docs: `README-CICD.md`, `specs/podman-single-host-design.md`, `specs/zebra-as-is.md` §6–7, `AGENTS.md`, `specs/AGENTS.md`
- [x] 3.4 Run lint + format (`uv run ruff check --fix . && uv run ruff format .`)
- [x] 3.5 Push branch; green `lint → test → e2e` on the new runner

## 4. Go-live

- [x] 4.1 Merge to master; `deploy` + `smoke` green against prod Oracle
- [x] 4.2 Verify kill switch state and a single daemon; re-register passkey on the new RP ID (behind Access)
- [x] 4.3 GitLab housekeeping: delete stale runners, remove OKE-only CI variables
- [x] 4.4 Archive this change
