#!/usr/bin/env bash
# zebra-feedback.sh — submit a feature implementation to Zebra for review.
#
# Runs the review goal inside the production web container (rootless Podman,
# `zebra-web`) via `manage.py run_goal`, so it uses prod's database, workflows
# and API keys. Always exits 0 so it never blocks a commit; on failure it
# prints why.
#
# Usage:
#   bash scripts/zebra-feedback.sh <issue_number> "<feature title>" \
#     "- change 1
#   - change 2"
#
# Env:
#   ZEBRA_FEEDBACK_MODEL     model alias for the review (default: sonnet)
#   ZEBRA_FEEDBACK_CONTAINER container to run in (default: zebra-web)
set -uo pipefail

ISSUE="${1:-?}"
TITLE="${2:-feature}"
CHANGES="${3:-- (no summary provided)}"
MODEL="${ZEBRA_FEEDBACK_MODEL:-sonnet}"
CONTAINER="${ZEBRA_FEEDBACK_CONTAINER:-zebra-web}"

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

if ! command -v podman >/dev/null 2>&1 \
  || [ "$(podman inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]; then
  echo "[zebra-feedback] Zebra server unreachable (container '$CONTAINER' not running) — skipping."
  exit 0
fi

echo "[zebra-feedback] Submitting to Zebra in '$CONTAINER' (model: $MODEL)..."

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
printf '%s' "$GOAL" >"$TMP/goal.txt"

# The goal goes in on stdin, so multiline text needs no quoting.
podman exec -i -w /app/zebra-agent-web "$CONTAINER" \
  sh -c 'python manage.py run_goal "$(cat)" --model "$1"' _ "$MODEL" \
  <"$TMP/goal.txt" >"$TMP/out.json" 2>"$TMP/err.log"
STATUS=$?

python3 - "$TMP/out.json" "$TMP/err.log" "$STATUS" "$ISSUE" <<'PY'
import json
import sys

out_path, err_path, status, issue = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
raw = open(out_path).read()
err_tail = "".join(
    line for line in open(err_path).readlines()[-15:] if " DEBUG " not in line
).rstrip()

try:
    d = json.loads(raw)
except ValueError:
    d = None

if not isinstance(d, dict) or not d.get("success"):
    print(f"[zebra-feedback] Goal execution failed (exit {status}) — skipping.")
    if isinstance(d, dict) and d.get("error"):
        print("Error:", d["error"])
    elif raw.strip():
        print("Output:", raw.strip()[:500])
    if err_tail:
        print("--- stderr (tail) ---")
        print(err_tail)
    sys.exit(0)

out = d.get("output")
text = None
if isinstance(out, dict):
    # Prefer the review text; skip goal echo and usage metadata
    skip = {"goal", "run_id", "workflow_name"}
    text = next(
        (v for k, v in out.items() if k not in skip and "usage" not in k and isinstance(v, str)),
        None,
    )
elif out:
    text = str(out)

print("")
print(f"=== Zebra Feedback (issue #{issue}) ===")
print(text or "No text output in response.")
print("=========================================")
PY
exit 0
