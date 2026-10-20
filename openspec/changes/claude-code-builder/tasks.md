Branch: `f98/claude-code-builder`

## 1. Host builder and sandbox

- [x] 1.1 `scripts/zebra_builder.py`: spool scan, job validation against ceilings + allowlist, clone, sandbox run, supervise (minutes, cancel), safe output reads, result + audit log, restart re-attach, publish (fresh clone, `git am`, push `zebra-build/*`, draft MR), prune
- [x] 1.2 `deploy/builder/Containerfile` + `sandbox-run.sh` (pinned Claude Code, non-root)
- [x] 1.3 Builder tests with a fake command runner (`zebra-agent-web/tests/unit/test_zebra_builder.py`); `--probe` sandbox escape check

## 2. Zebra side

- [x] 2.1 `zebra_tasks/builder/`: spool client, `claude_code_build`, `publish_build` actions + entry points + tests
- [x] 2.2 `zebra.forms.is_human_task`; web views use it
- [x] 2.3 `BuilderWatcher` (complete external waits, cancel orphaned jobs) + daemon tick hook + tests
- [x] 2.4 `build_software.yaml` workflow + workflow test with the builder faked

## 3. Deploy

- [x] 3.1 Quadlet units mount the spool; `deploy/podman/zebra-builder.service`
- [x] 3.2 `deploy-podman.sh`: `builder.env` from CI vars, sandbox image build, install + restart builder, spool dir created before web restarts

## 4. Docs and checks

- [x] 4.1 `specs/claude-code-builder-design.md`, `specs/zebra-as-is.md`, `specs/AGENTS.md`, `README-CICD.md` secrets
- [x] 4.2 Lint + format, full unit suite, `openspec validate claude-code-builder --strict`
- [ ] 4.3 Prod: token configured, a real small build reviewed and published as a draft MR
