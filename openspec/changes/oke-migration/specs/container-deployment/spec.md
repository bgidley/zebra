## ADDED Requirements

### Requirement: Workloads run as isolated OKE namespaces
Zebra's runtime SHALL be deployed on an OKE cluster with each concern in its own namespace: `prod` (live application), `tools` (the Claude Code sandbox), and a transient `smoke` namespace for validation. The `smoke` namespace MUST NOT be a permanent declared resource.

#### Scenario: Namespaces present after deploy
- **WHEN** the base manifests are applied to the cluster
- **THEN** namespaces `prod`, `tools`, and `ci` exist
- **AND** no `smoke` namespace exists outside of an in-progress smoke run

### Requirement: Prod web and budget daemon run as separate Deployments
The production application SHALL run as two Deployments — `zebra-web` (Daphne ASGI) and `zebra-daemon` (`manage.py run_daemon`) — so exactly one budget daemon runs independently of web replicas. The web Deployment MUST set `ZEBRA_DAEMON_AUTO_START=0` so the in-process daemon does not also start.

#### Scenario: Single daemon, independent of web
- **WHEN** the prod workloads are running
- **THEN** there is exactly one `zebra-daemon` pod executing the scheduler loop
- **AND** restarting or scaling `zebra-web` does not start an additional daemon

#### Scenario: Public ingress to web
- **WHEN** a client requests `/api/health/` via the prod Service load balancer
- **THEN** it receives a healthy response from a `zebra-web` pod

### Requirement: Private image registry with pull credentials
Container images SHALL be stored in private OCIR repositories and pulled using a Kubernetes `imagePullSecret`. The prod and smoke image SHALL be the same `zebra-web` image; the sandbox SHALL use a separate `zebra-claude` image.

#### Scenario: Cluster pulls a private image
- **WHEN** a workload references an OCIR image and the `ocir-pull` secret exists in its namespace
- **THEN** the image is pulled and the pod starts

### Requirement: Claude Code sandbox with persistent workspace
A long-lived `claude-code` Deployment SHALL provide an autonomous-agent and dev sandbox, with its working repository on a PersistentVolumeClaim and in-cluster `kubectl` access via a ServiceAccount (no kubeconfig secret).

#### Scenario: Workspace survives a pod restart
- **WHEN** the `claude-code` pod is recreated
- **THEN** files previously written under `/workspace` are still present

### Requirement: Reproducible, free-tier-shaped infrastructure
All cluster, network, registry, and IAM resources SHALL be defined as idempotent Terraform under `deploy/oke/`. The infrastructure MUST be shaped to fit Oracle Always-Free in steady state: an OKE Basic cluster, a single A1 node pool scalable to 4 OCPU / 24 GB, workers in a public subnet with an Internet Gateway (no paid NAT Gateway), and a single 10 Mbps flexible Load Balancer.

#### Scenario: Idempotent apply
- **WHEN** `terraform apply` is run twice with unchanged inputs
- **THEN** the second run reports no resource changes

#### Scenario: Secrets are never committed
- **WHEN** the repository is inspected
- **THEN** only `*.env.example` and `terraform.tfvars.example` templates are tracked
- **AND** real secret values and Terraform state are git-ignored
