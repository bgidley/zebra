> Branch: `f251/builder-stages`. Reference `#251` in commits (`Part of #251`: the epic continues).

## 1. Builder

- [x] 1.1 `zebra_builder.py`: `stage` / `branch` / `issue` / `approval` validation, `STAGE_TOKENS`, stage preambles
- [x] 1.2 Start: stage credentials by name, approval check before cloning, branch-aware clone
- [x] 1.3 Collect: report.json, host facts (ls-remote, compare, pipeline, merge parents), pushed-secret check, redaction of every credential; stages never published
- [x] 1.4 `--probe --stage`: real stage credentials, read-only whoami, `check_probe(report, stage)`

## 2. Sandbox and deploy

- [x] 2.1 `sandbox-run.sh`: credential helpers from env, `github` remote, no patch step for stages
- [x] 2.2 `Containerfile`: pinned, checksum-verified glab 1.119.0 and gh 2.103.2; openspec 1.13.2
- [x] 2.3 `deploy-podman.sh`: stage tokens into `builder.env`

## 3. Zebra side

- [x] 3.1 `BuilderSpool.submit_build` stage fields; `claude_code_build` stage inputs and merge approval

## 4. Tests

- [x] 4.1 Builder: validation, credentials per stage (incl. container name), approval, collect, merge, probe
- [x] 4.2 Actions: stage jobs, approval from ship record, refusals
- [x] 4.3 Local image build + `--probe --stage` for all five stages with the real tokens

## 5. Docs & delivery

- [x] 5.1 `specs/claude-code-builder-design.md`, `specs/zebra-as-is.md`, `README-CICD.md`, `zebra-tasks/AGENTS.md`
- [ ] 5.2 Zebra outcome feedback; push; green pipeline; merge; prod `--probe --stage` for all stages; archive; outcome review
