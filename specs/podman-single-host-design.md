# F117: Single-host Podman deployment

GitLab issue: [#117](https://gitlab.com/gidley/zebra/-/issues/117). Supersedes the OKE design (F108–F111, removed).

## 1. Goal & scope

Run prod (web + budget daemon) and CI on one OCI A1 instance under rootless Podman,
replacing the OKE cluster that was lost when a deploy severed the cluster the agent was
managing from inside it.

**In**: host bootstrap, Quadlet units, deploy/rollback script, pipeline rewrite, secrets flow.
**Out**: HA / multi-node, image registry, pre-deploy smoke against a separate schema
(smoke runs post-deploy against prod, as before OKE), the claude-code sandbox pod
(the agent now runs directly on the host).

## 2. Data model changes

None. Same Oracle ADB `Zebra` and schema; web runs migrations on start.

## 3. Interfaces

- `deploy/podman/bootstrap-host.sh` — idempotent host setup; `RUNNER_TOKEN=… ` also registers the runner.
- `scripts/deploy-podman.sh <tag>` / `--rollback`.
- Quadlet units `zebra-web.container`, `zebra-daemon.container` (image `localhost/zebra-web:prod`).
- CI jobs tagged `opc-shell`; `oke_*` jobs and `OKE_ENABLED` removed.

## 4. Control flow

Deploy: write `prod.env` → build `:<sha>` → install units → stop daemon → `:prod`→`:previous`,
`:<sha>`→`:prod` → `restart zebra-web` (`Notify=healthy`, so it returns only once
`/api/health/` passes, after migrations) → start daemon → smoke user → prune.
Failure at the health step re-promotes the previous image and fails the job.

Invariants:
- **One daemon**: a single systemd unit; stopped before the swap, started after web is
  healthy; web has `ZEBRA_DAEMON_AUTO_START=0`. Two daemons would double-run goals.
- **Blast radius**: the deploy touches only the two `zebra-*` user units. Runner,
  sshd, Tailscale and host networking are never restarted by CI.
- **Resource caps**: web 1.5 GB, daemon 768 MB, runner `concurrent = 1`, so a
  runaway job or container cannot OOM the host that also runs the agent.

## 5. Configuration

| Item | Location |
|---|---|
| Secrets (`ORACLE_*`, `ANTHROPIC_API_KEY`, `KAGI_API_KEY`) | GitLab CI variables → `~/.config/zebra/prod.env` (0600, regenerated per deploy) |
| `DJANGO_SECRET_KEY` | generated once → `~/.config/zebra/django_secret_key` |
| WebAuthn origin, CSRF, budget, model | `~/.config/zebra/site.env` (from `deploy/podman/site.env.example`) |
| `KEEP_IMAGES` | deploy script env, default 5 |

Access: `tailscale serve` → `127.0.0.1:8000`. The Tailscale hostname stays `zebra-oke`
so passkeys bound to `zebra-oke.tailf1e473.ts.net` keep working.

## 6. Open questions / risks

- Single point of failure: host loss means rebuild from `bootstrap-host.sh` (≈15 min).
- CI jobs share the prod host's CPU; long test runs can slow prod briefly.
- `E2E_PROVISIONER_*` are not set in GitLab, so `e2e` runs on the SQLite fallback.
- The ADB access list includes `0.0.0.0/0` plus stale OKE VCN entries; it should be narrowed.
- `ORACLE_*` CI variables are unprotected, so they reach feature-branch jobs too.
- No scheduled `e2e-live` pipeline exists yet.
