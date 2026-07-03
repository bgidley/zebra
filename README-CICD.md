# CI/CD

Zebra uses GitLab CI/CD with a **self-hosted Kubernetes executor on OKE** (Oracle Kubernetes Engine).
All pipeline jobs run in-cluster — nothing executes on GitLab's shared runners.

GitLab project: https://gitlab.com/gidley/zebra

## Pipeline overview

Every push to `master` with `OKE_ENABLED=true` runs nine stages in sequence:

```
lint  →  test  →  e2e  →  deploy  →  smoke  →  oke_build  →  oke_smoke  →  oke_deploy  →  oke_live
```

| Stage | What runs | Backend | Time |
|---|---|---|---|
| **lint** | `ruff check .` + `ruff format --check .` | — | ~3s |
| **test** | `pytest -m "not e2e"` (all packages) | SQLite | ~25s |
| **e2e** | `pytest zebra-agent-web/tests/e2e/ -m e2e` | Oracle E2E schema + cassette LLM | ~30s |
| **deploy** | *(no-op when OKE_ENABLED=true)* | — | — |
| **smoke** | *(no-op when OKE_ENABLED=true)* | — | — |
| **oke_build** | `docker build` + `docker push` to OCIR | — | ~2–5 min |
| **oke_smoke** | Ephemeral smoke namespace, own Oracle schema | Oracle smoke schema | ~2 min |
| **oke_deploy** | `kubectl set image` (rolling update) + prune OCIR | Oracle (prod) | ~1 min |
| **oke_live** | `pytest zebra-agent-web/tests/e2e_live/ -v` (real LLM + prod Oracle) | Oracle (prod) | ~10 min |

The `oke_*` stages are gated on `$OKE_ENABLED == "true"` (GitLab variable on `master` protected branch).

## Architecture

```
Your laptop  ──git push──▶  gitlab.com/gidley/zebra
                                    │
                         (runner polls outbound)
                                    │
                         OKE cluster (ns: ci)
                    ┌──────────────────────────────┐
                    │  gitlab-runner               │  Kubernetes executor
                    │  ├── lint / test / e2e       │  (ephemeral pods, tag: oke-k8s)
                    │  ├── oke_build               │
                    │  ├── oke_smoke               │
                    │  ├── oke_deploy              │  kubectl set image → ns:prod
                    │  └── oke_live_e2e            │  reads creds from zebra-prod-secrets
                    └──────────────────────────────┘
                                    │
                              OKE ns: prod
                    ┌──────────────────────────────┐
                    │  zebra-web (Daphne :8000)    │
                    │  zebra-daemon                │  separate Deployment
                    └──────────────────────────────┘
```

The runner runs as a Kubernetes executor — each job spawns an ephemeral pod and is torn down after.

## Secrets

Production Oracle and Anthropic credentials live in two places:

1. **K8s secret** `zebra-prod-secrets` (namespace `prod`) — used by `oke_live_e2e` and the prod pods:
   ```bash
   kubectl -n prod get secret zebra-prod-secrets -o jsonpath='{.data.ORACLE_DSN}' | base64 -d
   ```

2. **GitLab CI/CD variables** (https://gitlab.com/gidley/zebra/-/settings/ci_cd → Variables):

| Variable | Used by |
|---|---|
| `ANTHROPIC_API_KEY` | e2e cassette recorder |
| `E2E_PROVISIONER_DSN` / `E2E_PROVISIONER_USERNAME` / `E2E_PROVISIONER_PASSWORD` | e2e (Oracle ephemeral schema) |
| `OKE_ENABLED` | gates all `oke_*` jobs |

## Stage details

### lint
```bash
uv sync --all-packages --frozen
uv run ruff check .
uv run ruff format --check .
```

### test (unit)
```bash
uv sync --all-packages --frozen
uv run pytest -m "not e2e" --ignore=zebra-agent-web/tests/e2e_live
```

Runs against SQLite (no `ORACLE_DSN` injected). Covers all four packages.

### e2e
Uses an **ephemeral Oracle schema** provisioned per-pipeline via `scripts/e2e_oracle_schema.py`.
The `E2E_PROVISIONER_*` credentials create a throwaway `E2E_<branch>_<pipeline-id>` Oracle user,
migrate into it, run the suite, and drop it in `after_script`.

LLM responses are replayed from cassettes in `zebra-agent-web/tests/e2e/cassettes/`.
To re-record, run with `VCR_RECORD_MODE=rewrite` (requires real API key).

If `E2E_PROVISIONER_*` variables are absent (e.g. local development), falls back to SQLite
(`--ds=zebra_agent_web.e2e_settings`).

### oke_build
```bash
docker build -t $OCIR_REGISTRY/zebra/zebra-web:$CI_COMMIT_SHORT_SHA .
docker push $OCIR_REGISTRY/zebra/zebra-web:$CI_COMMIT_SHORT_SHA
```
Builds the multi-stage `Dockerfile` and pushes to OCIR (Oracle Container Image Registry).

### oke_smoke
Deploys the new image to an ephemeral `smoke-<sha>` namespace with its own Oracle schema,
runs `pytest zebra-agent-web/tests/e2e/ -m e2e` against it, tears down on completion.
Failed smoke **blocks `oke_deploy`**.

### oke_deploy
```bash
kubectl -n prod set image deployment/zebra-web zebra-web=$OCIR_REGISTRY/zebra/zebra-web:$CI_COMMIT_SHORT_SHA
kubectl -n prod set image deployment/zebra-daemon zebra-daemon=$OCIR_REGISTRY/zebra/zebra-web:$CI_COMMIT_SHORT_SHA
kubectl -n prod rollout status deployment/zebra-web
kubectl -n prod rollout status deployment/zebra-daemon
```
Triggers a rolling update; waits for rollout to complete. `resource_group: oke-prod` ensures
only one deploy runs at a time.

### oke_live (post-deploy smoke)
```bash
# Pull creds from the prod k8s secret
export ORACLE_DSN="$(kubectl -n prod get secret zebra-prod-secrets -o jsonpath='{.data.ORACLE_DSN}' | base64 -d)"
export ORACLE_USERNAME="$(kubectl -n prod get secret zebra-prod-secrets -o jsonpath='{.data.ORACLE_USERNAME}' | base64 -d)"
export ORACLE_PASSWORD="$(kubectl -n prod get secret zebra-prod-secrets -o jsonpath='{.data.ORACLE_PASSWORD}' | base64 -d)"
export ANTHROPIC_API_KEY="$(kubectl -n prod get secret zebra-prod-secrets -o jsonpath='{.data.ANTHROPIC_API_KEY}' | base64 -d)"
uv run pytest zebra-agent-web/tests/e2e_live/ -v
```
Runs 12 real-LLM tests against the live prod Oracle schema. Results prove the deployed system
works end-to-end. Runs on tag `oke-k8s` (in-cluster runner has `kubectl` access to `prod` ns).

## Runner configuration

The runner is deployed in OKE namespace `ci` as a Kubernetes executor.

Key facts:
- **Executor**: Kubernetes (each job = ephemeral pod)
- **Tag**: `oke-k8s` (all OKE jobs carry this tag)
- **Namespace**: `ci`
- **RBAC**: can `kubectl set image` on `prod` deployments; can read `prod` secrets for `oke_live`
- **Manifests**: `k8s/base/gitlab-runner/`
- **Registration**: `deploy/oke/scripts/60-register-runner.sh`

To check runner status:
```bash
kubectl -n ci get pods -l app=gitlab-runner
kubectl -n ci logs deploy/gitlab-runner --tail=50
```

To re-bootstrap, run `deploy/oke/scripts/60-register-runner.sh` against the cluster.

## Key files

| File | Purpose |
|---|---|
| `.gitlab-ci.yml` | Pipeline definition (all 9 stages) |
| `Dockerfile` | Multi-stage image build |
| `k8s/base/gitlab-runner/` | GitLab Runner Kubernetes manifests |
| `k8s/base/prod-web/` | `zebra-web` Deployment + Service + Ingress |
| `k8s/base/prod-daemon/` | `zebra-daemon` Deployment (separate pod, same image) |
| `deploy/oke/scripts/60-register-runner.sh` | One-shot runner registration |
| `deploy/oke/scripts/e2e_oracle_schema.py` | Ephemeral E2E Oracle schema provisioner |
| `zebra-agent-web/tests/e2e/cassettes/` | Recorded LLM interactions for e2e tests |
| `zebra-agent-web/tests/e2e_live/` | Real-LLM live tests (run post-deploy) |
