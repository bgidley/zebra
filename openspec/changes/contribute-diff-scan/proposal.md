## Why

#282 lets an onboarded Zebra propose pull requests from its own GitHub fork of `bgidley/zebra`.
The leak guard (#237) and the Commons scans (#229, #236) check workflow YAML, not code diffs, so
nothing stops a contributed patch carrying a secret, a key file or someone's personal data out of
the instance. Slice A (282-A) adds that check, on its own, before the fork, token and PR slices
(282-B to 282-E) exist. No workflow uses it yet; it changes nothing in prod.

## What Changes

- New task action `contribute_diff_scan` (`zebra_tasks/contribute/diff_scan.py`,
  `always_reversible`, read-only, one low-tier LLM call). Inputs: a unified diff, commit messages,
  PR title and body, author name and email, the contributor's GitHub login (and id).
- It parses the diff and scans **only added lines** (plus file paths, commit messages, PR text and
  the author name; anything outside a hunk is scanned too, never dropped):
  - the Commons personal-data rules (`pii_scan.rule_findings`) and confidentiality rules
    (`confidentiality.confidential_rule_findings` without the generic URL, `key: value`
    credential and attribute-matching internal-host rules, which fire on ordinary code; a
    code-aware host rule replaces the last) plus `ZEBRA_SYNC_CONFIDENTIAL_PATTERNS`, the
    sync service's patterns and the task's `patterns`;
  - secret rules: GitHub, OpenRouter / Anthropic / OpenAI, GitLab, Slack, Google, AWS keys, JWTs,
    any `-----BEGIN … -----` block, OCI `ocid1.(tenancy|user|key|credential)`, quoted secret
    literals, and high-entropy strings of 32+ characters;
  - blocked files: `.env*`, `*.pem`, `*.key`, `site.env`, key stores, credential directories
    (`.ssh/`, `.aws/`, `.oci/`, `.gnupg/`, `commons-keys/`, …) and binaries;
  - `SENSITIVE_PATHS` (CI, deploy, scripts, Docker) are **flagged** for the owner, not blocked;
  - a size cap (`max_chars`) and one low-tier LLM pass for names, addresses, health and other
    personal details the rules miss.
- It **fails closed**: route `clean` only when the diff parses, no rule fires and the LLM answers
  `personal_data: false`; an empty or malformed diff, too much text, no LLM, an empty or unusable
  reply all route `rejected`. Findings are masked and located (`file:line`).
- The result carries the author email rewritten to the GitHub noreply address and the diff's
  sha256 (for the approval binding in 282-C).

## Capabilities

### New Capabilities
- `contribute-diff-scan`: the diff scanner action, its rules, fail-closed routing and output.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A diff that adds a secret (each detector: GitHub, OpenRouter/Anthropic, `nsec1`, `-----BEGIN`, OCI ocid, AWS, JWT, high-entropy), personal data (email, phone, postcode, a confidential pattern) or a blocked file (`.env`, `*.pem`, `*.key`, `site.env`, credential dirs, binary) routes `rejected` with a masked, located finding | One known-bad diff fixture per rule in `zebra-tasks/tests/test_contribute_diff_scan.py` |
| O2 | Only added content counts: the same secret on a removed or context line, or in a deleted file, does not reject; a secret in a commit message, the PR body or a path does | Tests |
| O3 | It fails closed: an empty or malformed diff, more than `max_chars`, no LLM, a failed call, an empty or verdict-less LLM reply all route `rejected` with `failed_closed: true`; an LLM `personal_data: true` rejects | Tests |
| O4 | A clean, real repo diff passes (`clean`), with CI / deploy paths listed in `sensitive_files`, the author email rewritten to `<id>+<login>@users.noreply.github.com` and the diff sha256 returned | Test over a real commit diff from this repo with a stub LLM answering `false` |
| O5 | The action is registered as `contribute_diff_scan`, `always_reversible`, and writes nothing but its own output property | `test_launch.py` source scan and reversibility tests pass; entry point test |
