# GitLab Runner bootstrap — Oracle VM (`opc`)

One-shot install for the self-hosted GitLab Runner that executes every job in
[`.gitlab-ci.yml`](../.gitlab-ci.yml). The runner runs on the Oracle Linux VM
reached via `ssh opc`, uses the **shell** executor, and runs as the `opc` user
so it inherits `~/.env`, the uv cache, and rootless Podman.

GitLab project: https://gitlab.com/gidley/zebra

## Prerequisites (already in place)

- `ssh opc` reaches the VM, `opc` has sudo.
- `/home/opc/.env` contains `ANTHROPIC_API_KEY`, `ORACLE_USERNAME`,
  `ORACLE_PASSWORD`, `ORACLE_DSN` (and wallet files if used).
- `uv` is installed and on `opc`'s PATH.
- The working copy lives at `/home/opc/zebra` with `origin` pointing at the
  GitLab fork.

## 1. Install packages

Oracle Linux ships Podman; `gitlab-runner` is installed from GitLab's
official RPM repo.

```bash
# GitLab Runner repo
curl -L "https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.rpm.sh" | sudo bash

sudo dnf install -y gitlab-runner podman
# podman-compose is a Python tool — install per-user with uv
uv tool install podman-compose
```

Verify:

```bash
gitlab-runner --version
podman --version
podman-compose --version
```

## 2. Create a project runner in GitLab

1. Open https://gitlab.com/gidley/zebra → **Settings → CI/CD → Runners**.
2. Click **New project runner**.
3. Tags: `opc-shell`. Run untagged jobs: **off**. Protected: **off** (deploy
   protection is handled by the pipeline `rules`, not runner visibility).
4. Copy the authentication token — you will not see it again.

## 3. Register the runner with the shell executor

```bash
sudo gitlab-runner register \
  --non-interactive \
  --url https://gitlab.com \
  --token "$RUNNER_AUTH_TOKEN" \
  --executor shell \
  --description "opc-oracle-vm" \
  --tag-list "opc-shell"
```

## 4. Run the runner as `opc`, not `gitlab-runner`

The default systemd unit runs jobs as a dedicated `gitlab-runner` user, which
does **not** have `/home/opc/.env`, the uv cache, or the rootless Podman
setup. Switch it over:

```bash
sudo systemctl stop gitlab-runner
sudo sed -i 's/^User=.*/User=opc/' /etc/systemd/system/gitlab-runner.service
sudo systemctl daemon-reload
sudo systemctl enable --now gitlab-runner
```

Then enable lingering so rootless Podman containers started by a deploy job
survive after the runner's user session ends:

```bash
sudo loginctl enable-linger opc
```

## 5. Set CI/CD variables in GitLab

In https://gitlab.com/gidley/zebra → **Settings → CI/CD → Variables**, add
the following as **Masked** and **Protected**:

| Variable           | Value (source)                          |
|--------------------|-----------------------------------------|
| `ANTHROPIC_API_KEY`| from existing `~/.env`                  |
| `ORACLE_USERNAME`  | from existing `~/.env`                  |
| `ORACLE_PASSWORD`  | from existing `~/.env`                  |
| `ORACLE_DSN`       | from existing `~/.env`                  |

These are exported into every job by the runner. `pytest-dotenv` and
`zebra_agent_web/settings.py` already read them from `os.environ`, so no
code change is needed.

## 6. Sanity checks (as `opc`)

```bash
ssh opc
systemctl status gitlab-runner           # active (running), User=opc
id                                       # uid=1000(opc)
podman ps                                # empty, no permission error
uv --version
cat /home/opc/.env | head -1             # readable
```

Then in GitLab → **Settings → CI/CD → Runners**, the runner tagged
`opc-shell` should show as online (green dot).

## 7. First pipeline

Push any commit to the GitLab fork. In **CI/CD → Pipelines**:

- `lint` → green
- `unit` → green
- `e2e` → green (uses Oracle + cassette LLM)
- `deploy` runs only on `master` pushes → `podman-compose up -d --build`

After a successful master deploy, on the VM:

```bash
podman ps                                # zebra-web running
curl -I http://localhost:8000/           # HTTP/1.1 200 OK (or 302 to login)
```

## 8. Schedules

Set up in GitLab → **CI/CD → Schedules**, not in `.gitlab-ci.yml`:

- **Nightly E2E live** — daily 02:00 UTC, branch `master`. Triggers the
  `e2e-live` job (real Anthropic API, no cassette) because the job's rule
  keys on `$CI_PIPELINE_SOURCE == "schedule"`. The `deploy` job is
  suppressed by the same mechanism (its rule requires `"push"`).

## Troubleshooting

- **Runner registered but jobs stuck in pending**: check the runner's tag
  matches `opc-shell`; the `default.tags` block in `.gitlab-ci.yml` will
  only schedule onto runners with that tag.
- **`podman-compose: command not found` in a job**: confirm `uv tool
  install podman-compose` ran as `opc`, and that `~/.local/bin` is on
  `opc`'s PATH (it should be via `uv`'s shell integration).
- **Oracle connection fails in `e2e` job but works interactively**: the
  runner's env may miss wallet paths. Copy wallet files into a location
  referenced by `ORACLE_DSN` and ensure they're readable by `opc`.
- **Deploy races on rapid merges**: `resource_group: zebra-prod` in the
  deploy job already serialises these; check the pipeline graph for the
  queued deploy.
