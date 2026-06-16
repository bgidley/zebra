# OKE Migration — Design

**Status:** Scaffolding (IaC written, not yet applied to any tenancy).
**Issue:** [F108 / #108](https://gitlab.com/gidley/zebra/-/issues/108) — migrate Zebra to Oracle Kubernetes Engine (GitLab).
**Code:** [`deploy/oke/`](../deploy/oke/) (Terraform + kustomize + scripts), [`docker/claude/Dockerfile`](../docker/claude/Dockerfile).

## 1. Goal & scope
Move Zebra off the single Always-Free VM (where prod, smoke, and Claude Code share
a host with no isolation and the disk fills up) onto **OKE** with three isolated
workloads and images in **OCIR**:

- **prod** (`ns: prod`) — `zebra-web` (Daphne) + `zebra-daemon` (budget daemon), always-on, public via the Always-Free 10 Mbps LB. Oracle **prod** schema.
- **smoke** (`ns: smoke`) — ephemeral per-CI-run instance + test execution against a dedicated Oracle **smoke** schema; deleted on completion. Replaces today's "smoke tests hit live prod".
- **claude-code** (`ns: tools`) — long-lived sandbox pod (autonomous agent + dev), repo on a PVC.

**Out of scope:** changing the Oracle ADB (still external), the workflow engine, or app code beyond running the daemon as its own process.

## 2. Data model / app changes
None to the domain model. One operational change: the budget daemon runs as a
**separate Deployment** (`manage.py run_daemon`) instead of the in-process
`DaemonStarterMiddleware`; prod web sets `ZEBRA_DAEMON_AUTO_START=0`. A dedicated
**smoke Oracle schema** is added (mirrors the `E2E_ORACLE_*` pattern).

## 3. Interface / deployment changes
- **Images**: two OCIR repos — `zebra/zebra-web` (existing `Dockerfile`, shared by prod + smoke) and `zebra/zebra-claude` (new sandbox image). Built rootless with **buildah**, tagged `:<sha>`.
- **IaC entrypoints**: `deploy/oke/Makefile` (`tooling/auth/infra/kubeconfig/secrets/build/deploy/smoke`) over numbered scripts; Terraform in `deploy/oke/terraform/`; kustomize in `deploy/oke/k8s/` (`base/` + `overlays/smoke`).
- **Secrets**: k8s Secrets generated from `deploy/oke/secrets/*.env` (git-ignored) — `zebra-prod-secrets`, `zebra-smoke-secrets`, `claude-secrets`, `ocir-pull`.
- **CI (next increment)**: GitLab Runner (Kubernetes executor) in `ns: ci`; pipeline `lint → test → e2e → build → smoke → deploy`, where deploy is `kubectl set image` of the smoke-validated `:<sha>` (build-once → validate → promote).

## 4. Control flow
`buildah build+push :<sha>` → `50-smoke.sh` (ephemeral smoke ns, own schema, run suite, teardown) → `40-deploy.sh` (`kustomize set image` + `kubectl apply`, rollout prod web/daemon + claude). Same image promoted; no rebuild.

## 5. Configuration
Terraform vars (`terraform.tfvars`): tenancy/user/region/compartment OCIDs, `region_key`, `node_ocpus`/`node_memory_gb` (2/12 migration → 4/24 cutover), `admin_cidr`. OKE **Basic** + Flannel CNI; workers in a public subnet + IGW (no paid NAT); single 10 Mbps LB. Env via the `*.env` secret files.

## 6. Open questions / risks
- **Parallel-week A1 overage** (~$5): the old VM holds the whole free A1 pool, so the migration node briefly bills; final state is free. Mitigate with the 2-OCPU node / temporary VM resize.
- **OCIR retention** has no stable Terraform resource → pruned from CI (keep last N).
- **Node image OCID** is auto-picked by a best-effort regex over `node_pool_option` sources; override with `node_image_ocid` if it mis-picks.
- **IAM** steps need a tenancy admin (dynamic groups/policies are tenancy-level) — see `deploy/oke/docs/oci-onboarding.md`.

See the cutover runbook: [`deploy/oke/scripts/99-migrate-cutover.md`](../deploy/oke/scripts/99-migrate-cutover.md).
