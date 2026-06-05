#!/usr/bin/env bash
# zebra-feedback.sh — submit a feature implementation to Zebra for review.
#
# Runs the goal directly via the project's Python environment using the same
# production Oracle database as the deployed container. Always exits 0.
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

GOAL="You are reviewing an implementation of a new feature in your own codebase.

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

OUTPUT=$(cd "$PROJECT_ROOT" && uv run python zebra-agent-web/manage.py run_goal \
  "$(printf '%s' "$GOAL")" \
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
    print(d.get('output') or d.get('error') or 'No output returned.')
except Exception:
    print(sys.stdin.read())
"
echo "========================================="
exit 0
