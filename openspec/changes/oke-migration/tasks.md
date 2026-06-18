> Branch: `f108/oke-migration` (per fN/short-description). Reference `#108` in commits.

## 1. Scaffold IaC (DONE — committed)

- [x] 1.1 Terraform: VCN/subnets/IGW/SGW, OKE Basic + Flannel, A1 node pool, OCIR repos, IAM, outputs, tfvars.example
- [x] 1.2 kustomize base: namespaces; prod-web Deployment + LB Service; prod-daemon Deployment; claude-code Deployment + PVCs + RBAC
- [x] 1.3 kustomize smoke overlay: ClusterIP instance wired to the smoke schema
- [x] 1.4 Scripts (00–50) + lib.sh + Makefile; cutover runbook (99)
- [x] 1.5 `docker/claude/Dockerfile`; secrets `*.env.example`; `docs/oci-onboarding.md`; `deploy/oke/README.md`
- [x] 1.6 `specs/oke-migration-design.md` + index; offline validation (bash -n, YAML, `kustomize build`)

## 2. OCI onboarding & infrastructure

- [ ] 2.1 Complete `docs/oci-onboarding.md` against a real tenancy; fill `terraform.tfvars` + `secrets/*.env`
- [ ] 2.2 `make tooling` + `make auth`; verify `oci iam region list`
- [ ] 2.3 `make infra`; confirm idempotent re-apply reports no changes (container-deployment: "Idempotent apply")
- [ ] 2.4 `make kubeconfig`; `kubectl get nodes` shows a Ready A1 node

## 3. Images to OCIR

- [ ] 3.1 `make secrets` (namespaces + Secrets + `ocir-pull`)
- [ ] 3.2 `BUILD_CLAUDE=1 make build`; verify both images pushed; test a private pull (container-deployment: "Cluster pulls a private image")

## 4. Deploy long-lived workloads

- [ ] 4.1 `make deploy TAG=<sha>`; `kubectl -n prod rollout status` for web + daemon
- [ ] 4.2 Verify exactly one daemon pod runs the scheduler loop; scaling web adds no daemon (container-deployment: "Single daemon")
- [ ] 4.3 Curl `/api/health/` via the LB; submit one goal end-to-end
- [ ] 4.4 Bring up claude-code; confirm `/workspace` persists across a pod restart; `claude --version`, `kubectl`, `glab`, `gh`

## 5. Smoke isolation validation

- [ ] 5.1 `make smoke TAG=<sha>`; suite passes against the smoke schema
- [ ] 5.2 Prove prod schema/budget unchanged during the run (release-promotion: "Prod untouched by smoke")
- [ ] 5.3 Confirm the `smoke` namespace is deleted afterward (release-promotion: "Ephemeral teardown")

## 6. CI on OKE

- [x] 6.1 GitLab Runner (Kubernetes executor) manifests in `k8s/base/gitlab-runner/` + `60-register-runner.sh` (apply/register at cutover)
- [x] 6.2 `.gitlab-ci.yml` gated `oke_build → oke_smoke → oke_deploy` (deploy = `kubectl set image` to `:<sha>`), behind `$OKE_ENABLED`; VM deploy/smoke gate off
- [x] 6.3 `prune-ocir.sh` (keep last N) wired into `oke_deploy`
- [ ] 6.4 Verify deploy is gated on smoke; failed smoke blocks deploy (release-promotion: "Deploy gated on smoke") — needs live cluster
- [ ] 6.5 Full pipeline green on the in-cluster runner — needs live cluster (F110)

## 7. Cutover & decommission

- [ ] 7.1 Run OKE prod alongside the VM; soak per `99-migrate-cutover.md`
- [ ] 7.2 Repoint DNS/users to the OKE LB
- [ ] 7.3 Terminate the old VM; scale node pool to 4 OCPU / 24 GB; confirm tenancy back within Always-Free

## 8. Docs, lint & ship

- [ ] 8.1 Update `specs/zebra-as-is.md` (deployment/CI now OKE) and `README-CICD.md`
- [ ] 8.2 Run `uv run ruff check . && uv run ruff format --check .`
- [ ] 8.3 Submit to prod Zebra via `scripts/zebra-feedback.sh`; incorporate feedback
- [ ] 8.4 Archive this OpenSpec change (`/opsx:archive`); `Closes #108` commit; open GitHub PR
