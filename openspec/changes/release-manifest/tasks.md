> Branch: `f283/release-manifest` (after `f283/release-versioning`). Commits `Part of #283`.

## 1. Manifest module

- [x] 1.1 `zebra_agent/release.py`: schema v1, cosign-format verify, `load_verified`
- [x] 1.2 `cryptography` direct dependency of `zebra-agent`

## 2. Tooling

- [x] 2.1 `scripts/release_manifest.py`: build (migrations since previous tag, notes), sign, verify, promote, publish, fetch
- [x] 2.2 `.gitlab-ci.yml`: `release:manifest`, `release:promote-stable` (tag-only, dormant until configured)

## 3. Tests and docs

- [x] 3.1 `zebra-agent/tests/test_release_manifest.py` (schema, tamper, other key, promote, publish, CI rules)
- [x] 3.2 `specs/release-pipeline-design.md`, `specs/zebra-as-is.md`, `README-CICD.md`, `zebra-agent/AGENTS.md`
- [x] 3.3 `uv run ruff check --fix . && uv run ruff format .`

## 4. Delivery

- [ ] 4.1 Branch pipeline green; merge; master pipeline green with no manifest jobs
- [ ] 4.2 Owner: key pair + `deploy/release/cosign.pub`, bucket, `v*` protected tags (with R2)
