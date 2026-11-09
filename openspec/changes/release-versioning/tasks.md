> Branch: `f283/release-versioning`. Commits `Part of #283` (R1 of R1–R3).

## 1. Version

- [x] 1.1 `gen_version.py`: `version` from `describe`, shallow-clone tag fetch
- [x] 1.2 `api/version.py` fallback `version`; footer shows the release

## 2. Tagging

- [x] 2.1 `scripts/release_tag.py`: next version, green-master guards, notes, GitLab release
- [x] 2.2 `.gitlab-ci.yml`: `release` stage, manual `release:tag` job

## 3. Tests and docs

- [x] 3.1 Tests: `test_release_tag.py` (versions, notes, guards, CI rules, gen_version), `test_version.py`
- [x] 3.2 `README-CICD.md`, `specs/zebra-as-is.md`
- [x] 3.3 `uv run ruff check --fix . && uv run ruff format .`

## 4. Delivery

- [ ] 4.1 Branch pipeline green; merge; master pipeline green with `release:tag` manual
- [ ] 4.2 Owner adds `RELEASE_GITLAB_TOKEN` (masked, protected) before the first release
