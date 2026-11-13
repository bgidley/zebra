## Context

Plan: `plan-281-282` slice 282-A (#282). Sibling of the leak guard (#237) and the Commons scans
(`commons_pii_scan`, `commons_confidentiality_scan`), which it reuses. Consumer: the
*Contribute Upstream* workflow (282-C), which runs it after the builder's `patch` stage and again
inside `contribute_open_pr` on the approved bytes.

## Decisions

- **Placement**: `zebra-tasks/zebra_tasks/contribute/diff_scan.py`, beside `commons/`. A pure
  `scan_diff(...)` coroutine (LLM injected) plus the `ContributeDiffScanAction` wrapper, like
  `scan_confidential`. No store, no file or network access besides the LLM; `always_reversible`.
- **Diff parsing**: hunk headers give line counts, so a `+++`-looking added line is still an added
  line. Only `+` lines in hunks count as content; context and `-` lines are skipped. Every line
  outside a hunk that is not a known git header (a format-patch preamble, a trailer) is scanned as
  text, so nothing is silently dropped. A hunk that runs short or no file at all is malformed and
  fails closed.
- **Reuse with three exceptions**: the confidentiality rules' generic `url`, `credential`
  (`key: value`) and `internal_host` findings fire on ordinary code (`https://openrouter.ai`,
  `api_key = os.environ[...]`, `self.private`, `0.0.0.0`), so they are dropped here. A code-aware
  host rule replaces the last: corporate suffixes always, `.local` / `.private` / `.lan` only after
  a scheme or `@` or before a port, private IPs except loopback / unspecified. Codenames, customer
  names and confidential patterns stay.
- **Measured**: over the last 300 non-merge commits of this repo, 263 pass the rules; the rest
  are almost all the scanners' own test fixtures (fake emails, codenames, tokens), which a
  contribution should not carry anyway. Lock files get secret rules only (four-part versions read
  as IPs) and are not sent to the LLM; ISO timestamps are normalised (they read as phones).
- **Credentials** are covered by the stricter secret rules: quoted literals assigned to a
  secret-like name, credential URLs, known token formats and entropy.
- **Noreply emails**: `users.noreply.github.com` and `noreply.anthropic.com` are allowed (DCO and
  co-author trailers); every other address in scanned text is personal data.
- **Entropy rule**: a token of 32+ characters from `[A-Za-z0-9+/_-]` (plus `=` padding) with
  upper, lower and digit, and Shannon entropy ≥ 4.0 bits/char; a token with `/` is judged by its
  longest segment (20+); URL scheme/host/path are skipped (queries are not). Hex hashes,
  `NAME=hash`, paths and identifiers pass.
- **Blocked vs flagged**: blocked files reject; `SENSITIVE_PATHS` (same list as
  `scripts/zebra_builder.py`) only appear in `sensitive_files`. Deleted files are never blocked:
  deleting leaks nothing.
- **LLM**: one call, low tier, over added lines grouped per file plus commit messages and PR text.
  The author name is the contributor's chosen public identity (DCO), so it gets rules only.
  `personal_data: true` or any LLM finding rejects.

## Risks

- Rules miss secrets split across lines; LLM recall is imperfect. The owner's diff review in
  282-C stays mandatory.
- False positives block contributions (fail closed by design); the masked `file:line` findings
  tell the owner what to change.
