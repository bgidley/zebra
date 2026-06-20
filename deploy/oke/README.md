# Zebra on OKE — Infrastructure as Code

Migrates Zebra from the single Always-Free VM to **Oracle Container Engine for
Kubernetes (OKE)**, with three isolated workloads and images in **OCIR**:

| Workload | Namespace | Lifecycle | DB |
|----------|-----------|-----------|----|
| `zebra-web` + `zebra-daemon` (prod) | `prod` | always-on, **private** (ClusterIP; port-forward / internal LB / Tailscale) | Oracle **prod** schema |
| smoke instance + test run | `smoke` | **ephemeral** per CI run, then deleted | Oracle **smoke** schema |
| `claude-code` (agent + dev sandbox) | `tools` | always-on pod, repo on a PVC | — |

> **Status: scaffolding.** Nothing has been applied to any cloud account. The
> Terraform/manifests/scripts are ready to run once you complete onboarding.

```mermaid
flowchart LR
  subgraph build[buildah]
    W[zebra-web:sha]
    C[zebra-claude:sha]
  end
  W & C --> OCIR[(OCIR private registry)]
  OCIR --> P[prod ns: web + daemon]
  OCIR --> S[smoke ns: ephemeral, own Oracle schema]
  OCIR --> T[tools ns: claude-code pod]
  P -. private: port-forward / internal LB / Tailscale .- Users((admin))
  ADB[(Oracle ADB)] -. prod schema .- P
  ADB -. smoke schema .- S
```

## Layout
```
terraform/   OCI infra (VCN, OKE Basic, A1 node pool, OCIR, IAM)
k8s/         kustomize: base/{prod-web,prod-daemon,claude-code} + overlays/smoke
scripts/     00..50 bring-up + build/deploy/smoke; 99 cutover runbook
secrets/     *.env (git-ignored) → k8s Secrets; *.example committed
docs/        oci-onboarding.md (fresh-account guide)
Makefile     thin wrapper over scripts
```

## Quick start
1. **Onboarding** (one-time, manual): `docs/oci-onboarding.md`.
2. **Bring up infra**: `make all` (tooling → auth → infra → kubeconfig → secrets).
3. **Build + validate + deploy**:
   ```bash
   TAG=$(BUILD_CLAUDE=1 make build TAG=$(git rev-parse --short HEAD))
   make smoke  TAG=<sha>     # ephemeral, isolated; tears itself down
   make deploy TAG=<sha>     # promote the validated image to prod
   ```
4. **Migrate**: follow `scripts/99-migrate-cutover.md` (parallel week → cutover → decommission).

## Design notes
- **Build-once → smoke → promote**: the *same* `:sha` image that passes the smoke
  namespace is what `40-deploy.sh` rolls out to prod (`kustomize set image`). No rebuild.
- **Smoke isolation**: smoke runs in its own namespace against a dedicated Oracle
  schema and is deleted on exit — prod schema/budget are never touched.
- **Daemon split**: the budget daemon runs as its own `prod/zebra-daemon` Deployment
  (`manage.py run_daemon`, `Recreate` strategy) instead of the in-process
  `DaemonStarterMiddleware`, guaranteeing exactly one daemon.
- **Free-tier shape**: OKE **Basic** (free control plane), Flannel CNI, workers in a
  **public subnet + IGW** (no paid NAT), one A1 node sized 2/12 for migration → 4/24
  at cutover. Prod is **private** (ClusterIP, no public LB); the LB subnet/security
  list are scoped to the VCN for an optional future internal LB.
- **Registry hygiene**: OCIR has no stable Terraform retention resource; prune the
  registry from the CI deploy stage (keep last N) — replaces the old host-disk cleanup.
- **CI on OKE** (F109, scaffolded): GitLab Runner (Kubernetes executor) manifests in
  `k8s/base/gitlab-runner/` + `scripts/60-register-runner.sh`. `.gitlab-ci.yml` gains
  gated `oke_build → oke_smoke → oke_deploy` stages (build to OCIR → ephemeral smoke ns
  → `kubectl set image` promote + `prune-ocir.sh`), behind `$OKE_ENABLED == "true"`. While
  that flag is unset the existing VM `deploy`/`smoke` run unchanged; set it (and the VM jobs
  gate off) at cutover. Bring up: `make register-runner` (needs `GITLAB_RUNNER_TOKEN`).

## Verify without an account
`terraform -chdir=terraform init -backend=false && terraform -chdir=terraform validate`
and `kustomize build k8s/base` both run offline (no OCI calls) to sanity-check syntax.
