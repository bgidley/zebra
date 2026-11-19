## Why

Zebra's blind outcome review reads its own deployed source with `zebra_source`. The repo-root
`tests/` folder is neither copied into the prod image (`Dockerfile`) nor allowlisted in
`ALLOWED_TOP_LEVEL`, so an outcome whose evidence is a root test file comes back `[not_deployed]`,
the review marks it partial, and a human ruling task is opened (#300, from #279 and #282).

## What Changes

- The `Dockerfile` runtime stage copies `tests/` next to `specs/`, `scripts/` and `deploy/`.
- `tests` joins `ALLOWED_TOP_LEVEL` in `zebra_source`, so it can be listed, read and searched.
- A test guards that the image ships what the allowlist names.

## Non-goals

- A separate source snapshot for the reviewer, or shipping history (see design).
- Changing the other allowlist entries or the denied parts and suffixes.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | `zebra_source` can read a file under the repo-root `tests/` | unit test `test_root_tests_file_is_readable` |
| O2 | The prod image contains `tests/` | `Dockerfile` has `COPY tests/ tests/`; `podman exec zebra-web ls /app/tests/iac` after deploy |
| O3 | Image growth is negligible and no runtime behaviour changes | `du -sh tests` is 24K; only read-only files added, no entrypoint or env change |
| O4 | A blind review can read a repo-root test file in prod | after deploy, Read Zebra Source on `tests/iac/test_oci_plan_scan.py` succeeds |
