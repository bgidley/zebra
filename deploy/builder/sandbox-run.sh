#!/usr/bin/env bash
# Build sandbox entrypoint (#98): run Claude Code on /workspace, then leave the results in /out.
#
#   /out/prompt.md    in:  the job prompt (written by the host builder)
#   /out/claude.json  out: Claude Code's JSON result (turns, cost, summary)
#   /out/changes.patch, /out/diffstat.txt   out: everything committed since BASE_SHA
#   /out/test.log, /out/test.rc             out: TEST_COMMAND's output and exit code
#   /out/report.json  out: a delivery stage's own report (#251); the host checks the facts itself
#
# Env: MAX_TURNS, BASE_SHA, BUILD_TITLE, TEST_COMMAND, CLAUDE_CODE_OAUTH_TOKEN.
# Delivery stages (#251) also get STAGE, BRANCH, ISSUE, GITLAB_HOST, GITHUB_REPO and their
# credentials, GITLAB_TOKEN and/or GH_TOKEN, which glab and gh read from the environment.
set -uo pipefail
mkdir -p "$HOME"
cd /workspace || exit 1

git config --global user.name "Zebra (Claude Code)"
git config --global user.email "zebra@zebra.gidley.co.uk"
git config --global --add safe.directory /workspace

STAGE="${STAGE:-patch}"
if [ "$STAGE" != "patch" ]; then
  # Credential helpers read the tokens from the environment at push time; no token is written
  # to disk. The helpers answer only for their own host.
  if [ -n "${GITLAB_TOKEN:-}" ]; then
    git config --global "credential.https://${GITLAB_HOST:-gitlab.com}.helper" \
      '!f() { test "$1" = get && printf "username=oauth2\npassword=%s\n" "$GITLAB_TOKEN"; }; f'
  fi
  if [ -n "${GH_TOKEN:-}" ]; then
    git config --global "credential.https://github.com.helper" \
      '!f() { test "$1" = get && printf "username=x-access-token\npassword=%s\n" "$GH_TOKEN"; }; f'
    git remote add github "https://github.com/${GITHUB_REPO}.git" 2>/dev/null || true
  fi
fi

claude -p --output-format json --max-turns "${MAX_TURNS:-50}" \
  --dangerously-skip-permissions < /out/prompt.md > /out/claude.json 2> /out/claude.err
echo $? > /out/claude.rc

# A delivery stage pushes its own work; the host reads the result from the remote.
[ "$STAGE" != "patch" ] && exit 0

git add -A
if ! git diff --cached --quiet; then
  git commit -q -m "${BUILD_TITLE:-Zebra build}" -m "Uncommitted work left by Claude Code."
fi
git format-patch --stdout "${BASE_SHA}..HEAD" > /out/changes.patch
git diff --stat "${BASE_SHA}..HEAD" > /out/diffstat.txt

if [ -n "${TEST_COMMAND:-}" ]; then
  bash -c "$TEST_COMMAND" > /out/test.log 2>&1
  echo $? > /out/test.rc
fi
exit 0
