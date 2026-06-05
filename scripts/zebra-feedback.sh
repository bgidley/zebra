#!/usr/bin/env bash
# zebra-feedback.sh — submit a feature implementation to Zebra for review.
#
# Runs the goal via the project's Python environment, sharing the same
# production Oracle database. Always exits 0 so it never blocks a commit.
#
# Usage:
#   bash scripts/zebra-feedback.sh <issue_number> "<feature title>" \
#     "- change 1
#   - change 2"
set -euo pipefail

ISSUE="${1:-?}"
TITLE="${2:-feature}"
CHANGES="${3:-- (no summary provided)}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

GOAL="You are reviewing a new feature implementation in the Zebra codebase.

Feature: issue #${ISSUE} — ${TITLE}

Changes made:
${CHANGES}

Please review and provide concise feedback (under 200 words) on:
1. Does this implementation meet the stated requirements?
2. Is it as simple as it could be (XP simplicity principle)?
3. Are there gaps, risks, or missing test coverage?
4. Does it follow Zebra's architectural patterns (entry points, IoC, async, pluggable storage)?

Be direct and actionable."

echo "[zebra-feedback] Submitting to Zebra (model: haiku)..."

# Write goal to a temp file to avoid shell quoting issues with newlines
GOAL_FILE=$(mktemp /tmp/zebra-goal-XXXXXX.txt)
printf '%s' "$GOAL" > "$GOAL_FILE"
trap 'rm -f "$GOAL_FILE"' EXIT

OUTPUT=$(cd "$PROJECT_ROOT" && uv run python zebra-agent-web/manage.py run_goal \
  "$(cat "$GOAL_FILE")" \
  --model haiku 2>/dev/null) || {
  echo "[zebra-feedback] Goal execution failed — skipping."
  exit 0
}

echo ""
echo "=== Zebra Feedback (issue #${ISSUE}) ==="
echo "$OUTPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    out = d.get('output')
    if isinstance(out, dict):
        # Prefer explicit output keys; skip goal echo and usage metadata
        skip = {'goal', 'run_id', 'workflow_name'}
        text = None
        for k, v in out.items():
            if k in skip or 'usage' in k:
                continue
            if isinstance(v, str):
                text = v
                break
        print(text or 'No text output in response.')
    elif out:
        print(out)
    elif d.get('error'):
        print('Error:', d['error'])
    else:
        print('No output returned.')
except Exception as e:
    print('Parse error:', e)
    print(sys.stdin.read())
"
echo "========================================="
exit 0
