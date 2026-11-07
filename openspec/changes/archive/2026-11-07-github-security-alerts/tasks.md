> Branch: `f288/security-alerts`. Commit with `Closes #288`.

## 1. Process

- [x] 1.1 `scripts/github-security-alerts.sh`: wait for CodeQL on the merge sha, list open alerts, exit 0/2/1
- [x] 1.2 CLAUDE.md (`AGENTS.md`): **GitHub security alerts** section + final checklist item
- [x] 1.3 `.claude/agents/cicd-manager.md` step 11 + report line; `.claude/commands/cicd.md` step 3b + report

## 2. Dependencies

- [x] 2.1 Targeted `uv lock -P` for the 15 alerted packages (17 changed)
- [x] 2.2 Full unit suite green on the upgraded lock

## 3. CodeQL fixes

- [x] 3.1 Web views: generic 500s, escaped 4xx HTML, generic WebAuthn failure
- [x] 3.2 `goal_processing.html`: result link `href` via the DOM with an encoded run id
- [x] 3.3 `zebra_tasks.templating.strip_templates()`; leak guard, PII scan, confidentiality scan use it
- [x] 3.4 `apply_resolution`: no knowledge value in logs
- [x] 3.5 Tests: `test_templating.py`, queue-goal 500, WebAuthn verification failure

## 4. After merge

- [ ] 4.1 Dismiss the false positives on GitHub with reasons; dismiss the no-fix Twisted IMAP alert as `not_used`
- [ ] 4.2 Run `github-security-alerts.sh <merge sha>`: zero open, or follow-ups filed
- [x] 4.3 Sync `specs/zebra-as-is.md`
