#!/usr/bin/env bash
# github-security-alerts.sh — review GitHub's security alerts after a merge (#288).
#
# The GitHub mirror (bgidley/zebra) runs Dependabot, CodeQL (default setup, on every
# push to master and every PR) and secret scanning. Run this after every merge to
# master, once the master pipeline is green: it waits until CodeQL has analysed the
# merge commit, then lists every open alert. The baseline is zero open alerts, so
# anything listed is either new from this merge (fix it before sign-off) or must be
# fixed in a follow-up issue or dismissed on GitHub with a reason.
#
# Usage:
#   bash scripts/github-security-alerts.sh [<merge_sha>]
#
# Exit: 0 no open alerts; 2 open alerts (listed); 1 could not check (gh missing,
# not authenticated, API error). With a sha, a CodeQL analysis that has not
# arrived within the wait is a warning, not a failure: the alerts are still listed.
#
# Env:
#   GITHUB_SECURITY_REPO  repository (default: bgidley/zebra)
#   GITHUB_SECURITY_WAIT  seconds to wait for CodeQL on <merge_sha> (default: 900)
set -uo pipefail

REPO="${GITHUB_SECURITY_REPO:-bgidley/zebra}"
WAIT="${GITHUB_SECURITY_WAIT:-900}"
SHA="${1:-}"
LANGUAGES=("python" "javascript-typescript")

if ! command -v gh >/dev/null || ! command -v jq >/dev/null; then
  echo "github-security-alerts: needs gh and jq on PATH" >&2
  exit 1
fi
if ! gh api "repos/${REPO}" --jq .full_name >/dev/null 2>&1; then
  echo "github-security-alerts: cannot read ${REPO} (gh auth status?)" >&2
  exit 1
fi

# Wait for CodeQL to finish analysing the merge commit, one analysis per language.
if [[ -n "$SHA" ]]; then
  deadline=$((SECONDS + WAIT))
  while :; do
    done_langs=$(gh api "repos/${REPO}/code-scanning/analyses?ref=refs/heads/master&per_page=20" \
      --jq "[.[] | select(.commit_sha | startswith(\"${SHA}\")) | .category] | unique | join(\" \")" \
      2>/dev/null || true)
    missing=()
    for lang in "${LANGUAGES[@]}"; do
      [[ " ${done_langs} " == *"/language:${lang} "* ]] || missing+=("$lang")
    done
    ((${#missing[@]} == 0)) && { echo "CodeQL analysed ${SHA:0:7} (${LANGUAGES[*]})."; break; }
    if ((SECONDS >= deadline)); then
      echo "WARNING: no CodeQL analysis of ${SHA:0:7} for: ${missing[*]} after ${WAIT}s;" \
        "listing alerts as of the last analysis. Re-run later to cover this merge."
      break
    fi
    sleep 30
  done
fi

fetch() {  # fetch <endpoint> <jq row filter>
  gh api "repos/${REPO}/$1?state=open&per_page=100" --paginate --jq ".[] | $2"
}

status=0
total=0
section() {  # section <title> <endpoint> <jq row filter>
  local rows
  if ! rows=$(fetch "$2" "$3" 2>&1); then
    echo "## $1: could not list (${rows})"
    status=1
    return
  fi
  local n=0
  [[ -n "$rows" ]] && n=$(printf '%s\n' "$rows" | wc -l)
  total=$((total + n))
  echo "## $1: ${n} open"
  [[ -n "$rows" ]] && printf '%s\n' "$rows" | sort -t$'\t' -k2,2 | column -t -s$'\t'
}

section "Dependabot" dependabot/alerts \
  '[ "#\(.number)", .security_advisory.severity, .dependency.package.name,
     "\(.dependency.version_requirement // "") -> \(.security_vulnerability.first_patched_version.identifier // "no fix")",
     .security_advisory.summary ] | @tsv'
section "CodeQL" code-scanning/alerts \
  '[ "#\(.number)", (.rule.security_severity_level // .rule.severity), .rule.id,
     "\(.most_recent_instance.location.path):\(.most_recent_instance.location.start_line)",
     .rule.description ] | @tsv'
section "Secret scanning" secret-scanning/alerts \
  '[ "#\(.number)", "secret", .secret_type_display_name, .html_url ] | @tsv'

echo
echo "Alerts: https://github.com/${REPO}/security"
if ((status != 0)); then
  exit 1
fi
if ((total > 0)); then
  echo "${total} open alert(s): fix them, or file a follow-up issue / dismiss each on GitHub with a reason."
  exit 2
fi
echo "No open security alerts."
exit 0
