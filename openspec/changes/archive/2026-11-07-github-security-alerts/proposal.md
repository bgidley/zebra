## Why

The GitHub mirror (`bgidley/zebra`) runs Dependabot, CodeQL and secret scanning, but nothing in the
delivery flow looks at them, so alerts pile up unseen. On 2026-11-07 there were 103 open Dependabot
alerts (`uv.lock` had never been version-upgraded: anyio TLS spoofing (critical), DRF, Twisted /
daphne / autobahn, urllib3, cryptography, Django, sqlparse, …) and 38 CodeQL alerts, a handful of
them real. GitLab #288.

## What Changes

- **Process**: `scripts/github-security-alerts.sh [<merge sha>]` waits for CodeQL to analyse the
  merge commit, then lists every open Dependabot, CodeQL and secret-scanning alert (exit 0 none,
  2 open, 1 could not check). CLAUDE.md (new **GitHub security alerts** section + the final
  checklist), the `cicd-manager` agent (step 11 + report) and `/cicd` (step 3b) run it after every
  merge to master. Baseline is zero open alerts: an alert a change introduced is fixed before
  sign-off; the rest are fixed, filed (`security` label) or dismissed with a reason.
- **Dependencies**: targeted `uv lock -P` upgrade of every package with an alert (17 packages);
  no blanket upgrade (that pulled unrelated majors: openai 3, oracledb 26, redis 8, webauthn 3).
- **CodeQL fixes**:
  - Web views no longer return exception text: 500s say "see the server log" (the exception is
    logged), 4xx HTML responses escape it, WebAuthn verification says only "Verification failed".
  - `goal_processing.html` sets the result link's `href` from an encoded run id, not `innerHTML`.
  - `strip_templates()` (`zebra_tasks.templating`) replaces the quadratic lazy `{{.*?}}` regex in
    the leak guard, PII scan and confidentiality scan with a linear scan (same result).
  - `apply_resolution` no longer logs the user's knowledge value.
- **False positives dismissed** on GitHub with a reason: `yaml.load` with a `SafeLoader` subclass,
  credential-store logs without the secret, the relay `--keygen` printing the key it was asked for,
  URL-substring assertions in tests, 4xx JSON validation messages meant for the caller.

## Capabilities

### New Capabilities
- `security-alert-review`: post-merge review of GitHub security alerts, and the code-level rules
  the CodeQL fixes establish (no exception text to clients, linear template stripping, no personal
  values in logs).

### Modified Capabilities
None.

## Impact

`scripts/`, `AGENTS.md` (CLAUDE.md), `.claude/agents/cicd-manager.md`, `.claude/commands/cicd.md`,
`uv.lock`, `zebra-agent-web` API views + one template, `zebra-tasks` templating / leak guard / PII
and confidentiality scans / `apply_resolution`. No data model or setting changes.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Every merge to master ends with a GitHub security alert review that waits for CodeQL on the merge commit | `scripts/github-security-alerts.sh` (exit 0/2/1); CLAUDE.md section + checklist, `cicd-manager` step 11 + report line, `/cicd` step 3b; this change's own merge runs it |
| O2 | No Dependabot alert stays open for a dependency with a fixed release | `uv.lock` pins the fixed versions; after the merge the script lists no Dependabot alert except ones dismissed with a reason (no-fix Twisted IMAP ReDoS, IMAP unused) |
| O3 | The real CodeQL findings are fixed: no exception text in web responses, no `innerHTML` run id, no quadratic template regex, no knowledge value in logs | Tests: `test_templating.py` (same result as the regex, linear on 200k `{{`), queue-goal 500 and WebAuthn failure hide the exception; CodeQL closes those alerts on the merge commit |
| O4 | Every remaining CodeQL alert is dismissed with a written reason, so the baseline is zero open | `github-security-alerts.sh` exits 0 after the merge (or lists only alerts filed as follow-ups) |
| O5 | The upgrade does not break prod | Full unit + e2e green on the branch and master; prod `short_hash` = merge; smoke green |
