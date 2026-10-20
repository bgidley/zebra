#!/usr/bin/env bash
# Build sandbox entrypoint (#98): run Claude Code on /workspace, then leave the results in /out.
#
#   /out/prompt.md    in:  the job prompt (written by the host builder)
#   /out/claude.json  out: Claude Code's JSON result (turns, cost, summary)
#   /out/changes.patch, /out/diffstat.txt   out: everything committed since BASE_SHA
#   /out/test.log, /out/test.rc             out: TEST_COMMAND's output and exit code
#
# Env: MAX_TURNS, BASE_SHA, BUILD_TITLE, TEST_COMMAND, CLAUDE_CODE_OAUTH_TOKEN.
set -uo pipefail
mkdir -p "$HOME"
cd /workspace || exit 1

git config --global user.name "Zebra (Claude Code)"
git config --global user.email "zebra@zebra.gidley.co.uk"
git config --global --add safe.directory /workspace

claude -p --output-format json --max-turns "${MAX_TURNS:-50}" \
  --dangerously-skip-permissions < /out/prompt.md > /out/claude.json 2> /out/claude.err
echo $? > /out/claude.rc

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
