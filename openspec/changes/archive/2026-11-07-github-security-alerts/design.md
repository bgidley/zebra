## Context

GitLab is canonical and runs CI; GitHub is a mirror whose security features (Dependabot, CodeQL
default setup on master + PRs, secret scanning) were never part of the flow. #288.

## Decisions

- **Review after merge, not as a CI gate.** CodeQL runs on GitHub after the master push, outside
  GitLab CI, and Dependabot alerts appear when advisories are published, not when code changes. A
  CI gate would fail on alerts unrelated to the branch. The review is a step of the merge
  checklist (`github-security-alerts.sh`), alongside the outcome review.
- **The script waits for the merge commit's analyses** (`code-scanning/analyses` filtered by
  `commit_sha`, one per language: python, javascript-typescript), up to 15 min, then warns and
  lists anyway: a slow analysis must not block sign-off silently.
- **Zero baseline.** Getting to zero (fix or dismiss with a reason) makes "anything listed" a
  signal. Dismissing a real finding to reach zero is forbidden in CLAUDE.md.
- **Targeted lock upgrade.** `uv lock --upgrade` changed 61 packages including majors of openai,
  oracledb, redis and webauthn; `-P` on the 15 alerted packages changes 17 (two transitive).
- **Exception text policy.** 500s: generic message, exception logged with `logger.exception`.
  4xx HTML: escaped exception text (they are user-facing validation messages). 4xx JSON domain
  errors stay as they are (DRF JSON is not an XSS vector; the message is the API's contract);
  their CodeQL alerts are dismissed as "won't fix".
- **`strip_templates()`** keeps the exact semantics of `re.sub(r"\{\{.*?\}\}", " ", s, flags=re.S)`
  (non-overlapping, leftmost, an unclosed `{{` left as is) with `str.find`, so leak-guard and scan
  results do not change.

## Risks

- Django 6.0 → 6.1, DRF 3.18, Twisted 26, cryptography 50: covered by the unit + Oracle e2e suites
  and smoke; rollback is a revert of `uv.lock`.
- `ujson` 6 is a transitive dependency; no direct use in Zebra.
- The Twisted IMAP ReDoS has no fixed release; Zebra does not use `twisted.mail`. Dismissed as
  `not_used`.
