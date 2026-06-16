## Context

Zebra runs on a single Always-Free Ampere A1 VM (4 OCPU / 22 GB). Prod is a podman
container; Claude Code runs bare on the host; smoke tests (GitLab shell executor) hit
the live prod instance, writing to the prod Oracle schema and spending prod budget. The
disk runs ~95% full from repeated `--no-cache` builds. The full design narrative and the
scaffolding already implemented live in `specs/oke-migration-design.md` and `deploy/oke/`.
Constraint: stay inside Oracle Always-Free in steady state. Closes #108.

## Goals / Non-Goals

**Goals:**
- Three isolated workloads on OKE: prod (web + daemon), ephemeral smoke (own schema), claude-code sandbox.
- All infrastructure reproducible as IaC (Terraform + kustomize + scripts).
- Build-once → smoke-validate → promote release flow; prod image == validated image.
- Free-tier steady state.

**Non-Goals:**
- No change to the Oracle ADB, the workflow engine, app domain code, or web UX.
- No multi-node / HA / autoscaling; single A1 node, one replica per workload.
- No migration of historical workflow data beyond what already lives in Oracle (DB is external and unchanged).

## Decisions

- **OKE Basic + Flannel CNI, public worker subnet + IGW.** Basic control plane is free; Flannel uses fewer IPs than VCN-native; a public subnet with an Internet Gateway avoids a paid NAT Gateway. *Alternative:* private subnet + NAT (rejected: NAT bills; not free).
- **Split the budget daemon into its own Deployment** (`manage.py run_daemon`) instead of the in-process `DaemonStarterMiddleware`. Guarantees exactly one daemon, independent of web restarts/replicas — the correct k8s pattern. *Alternative:* single web pod with auto-start (rejected: couples daemon lifecycle to web, breaks with >1 replica).
- **Smoke as an ephemeral namespace against a dedicated Oracle schema**, torn down per run. *Alternative:* always-on staging instance (rejected: continuous resource cost; isolation only needs to exist during validation).
- **Build-once → promote via `kubectl set image` to `:<sha>`.** Guarantees the deployed artifact is byte-identical to the smoke-validated one. *Alternative:* rebuild at deploy (rejected: can't prove image identity).
- **buildah for image builds.** No Docker daemon in k8s; rootless and CI-friendly.
- **kustomize over Helm.** Built into kubectl; no extra dependency for a small object set.
- **Secrets as k8s Secrets from git-ignored `*.env`; OCIR retention via a CI prune step** (no stable Terraform resource for OCIR retention).

## Risks / Trade-offs

- Parallel-run week exceeds the free A1 pool (old VM already uses all 4 OCPU) → ~$5 A1 overage. Mitigation: 2-OCPU migration node and/or temporarily resize the VM down; final state (VM gone, node 4/24) is free.
- Auto-picked OKE node image OCID (regex over `node_pool_option` sources) could mis-select → Mitigation: `node_image_ocid` override variable.
- Public k8s API endpoint and node SSH → Mitigation: locked to `admin_cidr` via security lists.
- IAM dynamic-groups/policies require tenancy-admin rights → Mitigation: documented bootstrap policy in `deploy/oke/docs/oci-onboarding.md`.

## Migration Plan

Per `deploy/oke/scripts/99-migrate-cutover.md`: (1) `make all` to stand up infra; (2) build/push images and run the ephemeral smoke validation; (3) bring up OKE prod alongside the still-live VM; (4) move CI into the cluster; (5) seed the claude-code pod; (6) repoint DNS/users to the OKE LB and soak; (7) terminate the VM and scale the node to 4/24. **Rollback:** the VM stays authoritative until DNS is repointed — abort by not using the LB IP; optionally `terraform destroy`.

## Data model / interface / docs notes

- **Data model:** no Django model or store-interface changes. New external Oracle **smoke** schema only.
- **Interface:** no new endpoints or task actions. New deployment interface (`deploy/oke/Makefile` targets, OCIR images, kustomize). `.gitlab-ci.yml` rewritten in a later increment.
- **specs/zebra-as-is.md:** update the deployment/CI description only once cutover lands (not during scaffolding), to avoid claiming a state that isn't live. The dedicated `specs/oke-migration-design.md` is referenced from the specs index now.

## Open Questions

- Exact OCIR retention depth (keep last N) and where the prune runs (deploy stage vs scheduled).
- Whether the in-cluster GitLab Runner uses OCIR or GitLab registry for the runner helper image.
