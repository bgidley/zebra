## Why

Contributors' Zebras open PRs against the GitHub mirror (bgidley/zebra) (#282). The canonical repo
and CI are on GitLab and the shell runner executes code on the prod host, so a maintainer must read
an imported diff before any CI runs. This change (slice D of #282) adds the maintainer import script.

## What Changes

- `scripts/import_github_pr.py` with `prepare` (fetch PR head, verify the Zebra-origin signature,
  re-scan the diff, create a local `fN/gh<PR>-slug` branch, push nothing), `push` (only with
  `--reviewed-sha` equal to the current head and a clean re-scan), and `reject` (close with comment).
- A Zebra-origin statement format (`<!-- zebra-origin npub/head/sig -->`, BIP-340 over
  sha256 of tag, repo and head sha) that slice C must emit.
- A diff-scanner interface: slice A's `zebra_tasks.contribute.diff_scan.scan_diff_text` is used when
  present, else a built-in fail-closed scan.
- CLAUDE.md section "Importing a GitHub PR".

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Importing a PR pushes nothing and starts no CI until the maintainer passes the reviewed sha | tests: prepare leaves the GitLab remote empty; push refuses a wrong sha |
| O2 | An unsigned, wrongly signed or re-pushed (head moved) PR is refused | tests on verify_origin and head mismatch |
| O3 | A diff with secrets, PII, blocked paths or a scanner error is refused | tests, fail closed |
| O4 | Contributor commits and authorship reach the GitLab branch unchanged | test compares author on the pushed commit |
