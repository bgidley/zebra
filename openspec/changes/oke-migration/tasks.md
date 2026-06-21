> Branch: `f108/oke-migration` (per fN/short-description). Reference `#108` in commits.

## 1. Scaffold IaC (DONE — committed)

- [x] 1.1 Terraform: VCN/subnets/IGW/SGW, OKE Basic + Flannel, A1 node pool, OCIR repos, IAM, outputs, tfvars.example
- [x] 1.2 kustomize base: namespaces; prod-web Deployment + LB Service; prod-daemon Deployment; claude-code Deployment + PVCs + RBAC
- [x] 1.3 kustomize smoke overlay: ClusterIP instance wired to the smoke schema
- [x] 1.4 Scripts (00–50) + lib.sh + Makefile; cutover runbook (99)
- [x] 1.5 `docker/claude/Dockerfile`; secrets `*.env.example`; `docs/oci-onboarding.md`; `deploy/oke/README.md`
- [x] 1.6 `specs/oke-migration-design.md` + index; offline validation (bash -n, YAML, `kustomize build`)

## 2. OCI onboarding & infrastructure

- [x] 2.1 OCI onboarding done against the real tenancy (uk-london-1); `terraform.tfvars` + `secrets/*.env` filled
- [x] 2.2 `make tooling` + `make auth`; oci/kubectl/terraform/kustomize/buildah installed, auth verified
- [x] 2.3 `make infra`; cluster + node pool + network + OCIR + IAM created (fixed: Service Gateway conflict, k8s version)
- [x] 2.4 `make kubeconfig`; A1 node Ready (v1.34.2)

## 3. Images to OCIR

- [x] 3.1 `make secrets` (namespaces prod/tools/ci + Secrets + `ocir-pull`)
- [x] 3.2 web + claude images built and pushed to OCIR; private pull works (prod/claude pods pulled)

## 4. Deploy long-lived workloads

- [x] 4.1 prod-web deployed; rollout Ready (prod-daemon deliberately held until cutover — avoids double-daemon vs the live VM)
- [x] 4.2 Single-daemon verification — `zebra-daemon` deployed to OKE (F111); SchedulerLoop started cleanly, resumed 24 interrupted processes, and correctly no-op'd on the goal queue ("Kill switch active — skipping pickup") since Ben halted the system-wide kill switch before this. Confirms the OKE daemon and the VM's in-process daemon can coexist safely while halted; VM daemon still needs to be structurally disabled (not just halted) before un-halting for real cutover
- [x] 4.3 `/api/health/` via LB `79.72.65.246` → 200
- [x] 4.4 claude-code up (claude/kubectl/git/gh + in-cluster RBAC); `glab` best-effort (skipped, non-blocking)

## 5. Smoke isolation validation

- [x] 5.1 smoke suite passes against the `ZEBRA_SMOKE` schema (4 passed / 2 skipped, incl. count-to-100)
- [x] 5.2 prod schema/budget untouched during the run (verified: prod health unchanged)
- [x] 5.3 `smoke` namespace deleted afterward (verified NotFound)

## 6. CI on OKE

- [x] 6.1 GitLab Runner (Kubernetes executor) manifests in `k8s/base/gitlab-runner/` + `60-register-runner.sh` (apply/register at cutover)
- [x] 6.2 `.gitlab-ci.yml` gated `oke_build → oke_smoke → oke_deploy` (deploy = `kubectl set image` to `:<sha>`), behind `$OKE_ENABLED`; VM deploy/smoke gate off
- [x] 6.3 `prune-ocir.sh` (keep last N) wired into `oke_deploy`
- [ ] 6.4 Verify deploy is gated on smoke; failed smoke blocks deploy (release-promotion: "Deploy gated on smoke") — needs live cluster
- [ ] 6.5 Full pipeline green on the in-cluster runner — runner is live and online (GitLab runner id 53800437, tag `oke-k8s`); fixed three bugs found while bringing it up: (1) missing `tags: [oke-k8s]` on `oke_build`/`oke_smoke`/`oke_deploy` — they silently inherited the VM's `default.tags: [opc-shell]`; (2) `gitlab/gitlab-runner:latest` needs to be fully-qualified (`docker.io/...`) — this cluster's container runtime enforces short-name resolution and rejects the ambiguous short name; (3) `gitlab-runner register` was passing `--tag-list`/`--locked`/`--run-untagged`, which GitLab rejects when registering with a runner *authentication* token (glrt-...) since those are server-side config on the runner object now. Still blocked: the runner's own RBAC (`k8s/base/gitlab-runner/rbac.yaml` — Role+RoleBinding in `ci`, plus cluster-scoped `oke-ci-deployer` ClusterRole/ClusterRoleBinding so build pods can deploy to `prod`/manage the ephemeral `smoke` namespace) needs cluster-admin to apply — `edit` doesn't cover `rbac.authorization.k8s.io` resources (by design, anti-privilege-escalation) nor cluster-scoped objects

## 7. Cutover & decommission

- [ ] 7.1 Run OKE prod alongside the VM; soak per `99-migrate-cutover.md`
- [ ] 7.2 Repoint DNS/users to the OKE LB
- [ ] 7.3 Terminate the old VM; scale node pool to 4 OCPU / 24 GB; confirm tenancy back within Always-Free

## 8. Docs, lint & ship

- [ ] 8.1 Update `specs/zebra-as-is.md` (deployment/CI now OKE) and `README-CICD.md`
- [ ] 8.2 Run `uv run ruff check . && uv run ruff format --check .`
- [ ] 8.3 Submit to prod Zebra via `scripts/zebra-feedback.sh`; incorporate feedback
- [ ] 8.4 Archive this OpenSpec change (`/opsx:archive`); `Closes #108` commit; open GitHub PR
