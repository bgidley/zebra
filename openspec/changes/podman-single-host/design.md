## Context

Narrative design: [`specs/podman-single-host-design.md`](../../../specs/podman-single-host-design.md). Host: OCI A1 `coding-agent`, OL9 aarch64, 2 OCPU / 10 GB, podman 5.8.

## Decisions

- **Quadlet over podman-compose** — systemd supervises restarts and boot start (linger); `Notify=healthy` makes `systemctl restart` a health gate; no extra Python tool in the deploy path.
- **Local image, no registry** — build on the host, tag `:<sha>` / `:prod` / `:previous`; rollback is a retag.
- **Secrets from GitLab CI variables** — regenerated into `~/.config/zebra/prod.env` (0600) on every deploy; GitLab stays the single source of truth. `DJANGO_SECRET_KEY` is generated once on the host.
- **Blast radius** — the deploy restarts only `zebra-web` / `zebra-daemon` user units; memory caps (1.5 GB / 768 MB) and runner `concurrent = 1` protect the runner, sshd and the agent.
- **One daemon** — single unit, stopped before the image swap and started only after web is healthy (migrations done).

## Data model / API changes

None. No new endpoints, tables or task actions.

## as-is sections to update

`specs/zebra-as-is.md` §6 (Daemon paragraph) and §7 (Deployment & CI/CD).

## Risks

Single point of failure (rebuild ≈15 min via bootstrap). CI shares CPU with prod. See design doc §6.
