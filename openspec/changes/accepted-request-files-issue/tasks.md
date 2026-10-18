> Branch: `f194/accept-files-issue`. Reference `#194` in commits.

## 1. Implementation

- [x] 1.1 `file_improvement_issue` action: skip rules, body + neutralising, GitLab POST, `filed_issue`, never fails
- [x] 1.2 `zebra_improvement_request.yaml` v2: `review → file_issue`; entry point
- [x] 1.3 Dedupe across all versions of the request workflow (#193 version part)
- [x] 1.4 `/dreams/` shows filed issue link or filing error
- [ ] 1.5 Deploy copies `ZEBRA_GITLAB_TOKEN` into prod.env; CI variable set

## 2. Tests & docs

- [x] 2.1 Action tests: accepted files, other verdicts / reviewer link / already filed skip, missing token, network error, non-2xx, neutralising
- [x] 2.2 Dedupe across versions test; workflow definition test
- [x] 2.3 `/dreams/` filed-issue and error tests
- [x] 2.4 `specs/zebra-as-is.md`, AGENTS docs, README-CICD, podman design, single-host spec
