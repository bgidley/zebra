#!/usr/bin/env bash
# zebra-feedback.sh — submit a feature implementation to production Zebra for review.
#
# Usage:
#   bash scripts/zebra-feedback.sh <issue_number> "<feature title>" \
#     "- change 1
#   - change 2"
#
# Exits 0 in all cases so it never blocks a commit.
set -euo pipefail

ISSUE="${1:-?}"
TITLE="${2:-feature}"
CHANGES="${3:-- (no summary provided)}"
BASE_URL="${ZEBRA_URL:-http://localhost:8000}"

if ! curl -sf "$BASE_URL/api/health/" > /dev/null 2>&1; then
  echo "[zebra-feedback] Production Zebra unreachable at $BASE_URL — skipping."
  exit 0
fi

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

RUN_ID=$(curl -sf -X POST "$BASE_URL/api/goals/" \
  -H "Content-Type: application/json" \
  -d "{\"goal\": $(printf '%s' "$GOAL" | jq -Rs .), \"model\": \"haiku\"}" \
  | jq -r '.run_id // empty')

if [ -z "$RUN_ID" ]; then
  echo "[zebra-feedback] Goal submission failed — skipping."
  exit 0
fi

echo "[zebra-feedback] Submitted as run $RUN_ID — polling..."

RESULT='{}'
for i in $(seq 1 60); do
  RESULT=$(curl -sf "$BASE_URL/api/runs/$RUN_ID/status/" 2>/dev/null \
    || echo '{"status":"error"}')
  STATUS=$(echo "$RESULT" | jq -r '.status // "error"')
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] || [ "$STATUS" = "error" ]; then
    break
  fi
  sleep 5
done

echo ""
echo "=== Zebra Feedback (run $RUN_ID) ==="
echo "$RESULT" | jq -r '.output // .error // "No output returned."'
echo "======================================"
exit 0
