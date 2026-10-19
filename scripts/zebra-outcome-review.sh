#!/usr/bin/env bash
# zebra-outcome-review.sh — review a deployed change against its agreed outcomes (#190).
#
# Runs the "Outcome Review" workflow inside the prod web container: Zebra reviews
# the change blind (reading its own deployed source), compares its verdicts with
# Claude's, reconsiders once, and parks on a human task if they still disagree.
#
# Usage:
#   bash scripts/zebra-outcome-review.sh run <issue> "<title>" <outcomes.md> <claude.json> <base> [head]
#   bash scripts/zebra-outcome-review.sh status <process_id>
#
#   outcomes.md  the proposal's ## Outcomes table
#   claude.json  {"verdicts": [{"id": "O1", "verdict": "met|partial|missed", "evidence": "..."}]}
#   base, head   git refs; the reviewed diff is base..head (head defaults to HEAD)
#
# Exit codes: 0 review complete (agreed or ruled), 2 waiting on a human ruling
# (sign-off is blocked: poll with `status`), 1 the review failed or could not run.
#
# Env:
#   ZEBRA_REVIEW_MODEL       model tier (default: medium)
#   ZEBRA_FEEDBACK_CONTAINER container to run in (default: zebra-web)
#   ZEBRA_URL                base URL for task links (default: https://zebra.gidley.co.uk)
set -uo pipefail

MODEL="${ZEBRA_REVIEW_MODEL:-medium}"
CONTAINER="${ZEBRA_FEEDBACK_CONTAINER:-zebra-web}"
ZEBRA_URL="${ZEBRA_URL:-https://zebra.gidley.co.uk}"
MAX_DIFF_CHARS=60000

usage() {
  sed -n '9,11p' "$0" >&2
  exit 1
}

if ! command -v podman >/dev/null 2>&1 \
  || [ "$(podman inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]; then
  echo "[outcome-review] Zebra is unreachable (container '$CONTAINER' not running)." >&2
  exit 1
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

manage() {
  podman exec -i -w /app/zebra-agent-web "$CONTAINER" python manage.py run_workflow "$@" \
    2>"$TMP/err.log"
}

case "${1:-}" in
  run)
    [ $# -ge 6 ] || usage
    ISSUE="$2" TITLE="$3" OUTCOMES="$4" CLAUDE="$5" BASE="$6" HEAD="${7:-HEAD}"
    [ -f "$OUTCOMES" ] || { echo "[outcome-review] No outcomes file: $OUTCOMES" >&2; exit 1; }
    [ -f "$CLAUDE" ] || { echo "[outcome-review] No Claude review file: $CLAUDE" >&2; exit 1; }
    git diff "$BASE..$HEAD" >"$TMP/diff.patch" || exit 1
    HASH=$(podman exec "$CONTAINER" python -c \
      "import json; print(json.load(open('/app/version.json'))['short_hash'])" 2>/dev/null)

    python3 - "$ISSUE" "$TITLE" "$OUTCOMES" "$CLAUDE" "$TMP/diff.patch" "${HASH:-unknown}" \
      "$MAX_DIFF_CHARS" >"$TMP/in.json" <<'PY' || exit 1
import json
import sys

issue, title, outcomes, claude, diff_path, deployed, cap = sys.argv[1:]
diff = open(diff_path).read()
if len(diff) > int(cap):
    diff = diff[: int(cap)] + f"\n... diff truncated at {cap} characters; read the source for the rest"
try:
    claude_review = json.load(open(claude))
except ValueError as e:
    sys.exit(f"[outcome-review] {claude} is not JSON: {e}")
json.dump(
    {
        "goal": f"Outcome review of #{issue}: {title}",
        "issue": issue,
        "title": title,
        "outcomes": open(outcomes).read(),
        "claude_review": claude_review,
        "diff": diff,
        "deployed_hash": deployed,
    },
    sys.stdout,
)
PY
    echo "[outcome-review] Zebra is reviewing #$ISSUE at ${HASH:-unknown} (model: $MODEL)..." >&2
    manage "Outcome Review" --input-file - --model "$MODEL" <"$TMP/in.json" >"$TMP/out.json"
    ;;
  status)
    [ $# -ge 2 ] || usage
    manage --status "$2" >"$TMP/out.json"
    ;;
  *)
    usage
    ;;
esac

python3 - "$TMP/out.json" "$TMP/err.log" "$ZEBRA_URL" <<'PY'
import json
import sys

out_path, err_path, base_url = sys.argv[1:]
raw = open(out_path).read()
try:
    result = json.loads(raw)
except ValueError:
    print("[outcome-review] The review did not return JSON.")
    print(raw.strip()[:500])
    tail = [line for line in open(err_path).readlines()[-15:] if " DEBUG " not in line]
    print("".join(tail).rstrip())
    sys.exit(1)

status = result.get("status")
process_id = result.get("process_id")
if status == "awaiting_input":
    print("[outcome-review] BLOCKED: Zebra and Claude still disagree; a human ruling is needed.")
    print(f"Ruling task: {base_url}/tasks/{result.get('task_id')}/")
    print(f"Poll: bash scripts/zebra-outcome-review.sh status {process_id}")
    sys.exit(2)
if status != "complete":
    print(f"[outcome-review] Review {status}: {result.get('error')} (process {process_id})")
    sys.exit(1)

review = result.get("output") or {}
print(f"[outcome-review] {review.get('status', '?').upper()} (process {process_id})")
print()
print(review.get("table_markdown", ""))
if review.get("ruling"):
    print()
    print("Human ruling:")
    print(review["ruling"])
followups = review.get("followups") or []
if followups:
    print()
    print(f"Follow-up issues needed for: {', '.join(followups)}")
if review.get("status") == "ruled":
    print(f"Also check the ruling for disputed outcomes: {', '.join(review.get('disputed', []))}")
PY
