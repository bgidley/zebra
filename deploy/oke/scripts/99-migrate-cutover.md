# Migration & cutover runbook

Goal: move prod/smoke/claude-code off the single Always-Free VM onto OKE, running
**in parallel for ~1 week**, then decommission the VM. Each step is reversible up
to cutover.

> **Cost note:** the old VM already uses the whole free A1 pool (4 OCPU/24 GB). The
> parallel OKE node therefore incurs a small A1 charge (~$5 for a 2-OCPU node/week).
> Mitigate by keeping the migration node at 2 OCPU/12 GB (default) and/or temporarily
> resizing the old VM down. Final state (VM gone, node at 4/24) is back inside Always-Free.

## 1. Stand up infra (no traffic yet)
```bash
cd deploy/oke
make tooling && make infra && make kubeconfig && make secrets
```
If the tenancy refuses the extra A1 OCPUs, temporarily resize the old VM down
(Console → Instance → Edit shape → 2 OCPU) to free capacity, then re-run `make infra`.

## 2. Build, push, and validate in isolation
```bash
TAG=$(BUILD_CLAUDE=1 scripts/25-build-push.sh)   # → OCIR
SMOKE_PASSWORD=… scripts/50-smoke.sh "$TAG"       # ephemeral smoke ns, own schema, torn down
```
Smoke passing means the image is good. The old VM prod is still serving users.

## 3. Bring up OKE prod alongside the VM
```bash
scripts/40-deploy.sh "$TAG"
kubectl -n prod get svc zebra-web -o wide          # note the LB public IP
curl -sf http://<LB-IP>/api/health/
```
Exercise OKE prod via the LB IP while the VM keeps the real DNS. Confirm the
budget daemon pod logs its scheduler loop and a goal completes end-to-end.

## 4. Move CI into the cluster
Deploy the GitLab Runner (Kubernetes executor) into ns `ci`, register it, and run
a pipeline. Verify `lint → test → e2e → build → smoke → deploy` is green using the
in-cluster runner. (See `.gitlab-ci.yml` and README "CI on OKE".)

## 5. Bring up the claude-code pod
Already deployed by step 3 (`make deploy`). Seed its workspace:
```bash
kubectl -n tools exec -it deploy/claude-code -- bash
  git clone <repo> /workspace/zebra   # or restore from the VM
  claude --version && kubectl get ns
```
Confirm interactive Claude Code + one autonomous agent goal.

## 6. Cutover
- Repoint DNS / users from the VM to the OKE prod LB IP.
- Soak for the remainder of the parallel week; watch logs, budget, costs.

## 7. Decommission + reclaim free tier
```bash
# Terminate the old VM (Console or oci compute instance terminate).
# Then scale the node pool to the full free allowance:
sed -i 's/^node_ocpus.*/node_ocpus = 4/;s/^node_memory_gb.*/node_memory_gb = 24/' terraform/terraform.tfvars
make infra
```
Verify OCI **Cost Analysis** shows the tenancy back within Always-Free.

## Rollback (any time before step 6)
The VM is untouched and still authoritative until DNS is repointed. To abort,
just stop using the LB IP; optionally `terraform destroy` the cluster.
