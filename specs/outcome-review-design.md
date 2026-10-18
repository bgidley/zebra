# Outcome review (#190)

## Goal & scope

Put review at both ends of the delivery cycle. At the start, a feature agrees 3–5 observable
outcomes. After deploy, Zebra and Claude each review the shipped change against them without
seeing the other's verdicts, compare notes, and escalate lasting disagreement to a human as a
Zebra task. A session may not sign off while that task is open.

Out of scope: simultaneous wall-clock review (Claude's verdicts are an input; Zebra stays blind
until the comparison), and write access to source for Zebra. Trivial changes (docs-only, one-line
fixes) skip both steps. Decisions came from the workflow brainstorm linked on the issue.

## Data model

None. All state lives in process properties: inputs (`issue`, `title`, `outcomes`, `diff`,
`claude_review`, `deployed_hash`), `zebra_review`, `zebra_reconsidered`, and `review_result =
{status: agreed|disputed|ruled, rows, disputed, followups, table_markdown, dispute_notes, ruling?}`.

## Interfaces

| Piece | What it is |
|---|---|
| `## Outcomes` in `proposal.md` | Required by `openspec/config.yaml`: `#`, outcome, how we'll know. Posted on the issue |
| `scripts/zebra-feedback.sh` | Now reviews the proposed outcomes at the start (advisory, always exits 0) |
| `zebra_source` action | `operation: read` (line range, 12000-char cap) / `search` (regex, glob, 50 hits). Root `ZEBRA_SOURCE_ROOT` or the checkout above the installed `zebra_tasks` (`/app` in prod). Allowlist: the four packages, `specs`, `openspec`, `docs`, `scripts`, `deploy`, `pyproject.toml`, `version.json`, top-level `*.md`. Refuses dot-entries, `*.sqlite3`/`*.db`/keys, `tmp/`, `staticfiles/`, `fixtures/`, symlinks and anything resolving outside the root |
| *Read Zebra Source*, *Search Zebra Source* | Tool-only workflows around `zebra_source` for `llm_agent` |
| `compare_outcome_reviews` action | Parses both reviews (dict, list or fenced JSON), lines them up per outcome id, routes `agreed` / `disputed`. Missing, unknown or garbled verdicts are disputed, and every id in the outcomes table (`outcomes_key`) is compared, so an outcome neither reviewer judged is disputed too (#191). `reconsidered_key` overlays Zebra's second verdicts; `ruling_key` records the human ruling (`ruled`); `final` records without routing |
| *Outcome Review* workflow | System, tool-only (required `inputs`), `result_key: review_result` |
| `zebra_agent.direct_run` | `run_named_workflow()` creates and starts a named workflow from inputs (required inputs checked); `workflow_status()` → `complete` / `awaiting_input` / `failed` / `running` |
| `manage.py run_workflow` | `<name> --input-file - [--model sonnet]` or `--status <process_id>`; prints the status JSON, exits 1 on failure |
| `scripts/zebra-outcome-review.sh` | `run <N> <title> outcomes.md claude.json <base> [head]` builds the inputs on the host (diff capped at 60000 chars; deployed hash from `/app/version.json`) and runs the workflow in `zebra-web`; `status <process_id>` polls. Exit 0 complete, 2 waiting on a human, 1 failed. Tested with a fake `podman` in `zebra-agent/tests/test_outcome_review_script.py` (#192) |

## Control flow

```
zebra_review (llm_agent + source tools, JSON, blind)
  → compare ── agreed ──────────────────────────────→ finish (final)
            └─ disputed → zebra_reconsider (sees Claude's notes for disputed outcomes only)
                          → compare_again ── agreed ─→ finish
                                         └─ disputed → human_ruling (auto: false) → record_ruling
```

The human task shows the side-by-side table and both positions; the ruling is free text. It
appears on `/tasks/`. The process runs with a `run_id`, outside the Agent Main Loop (no
selection, metrics or memory).

Session side (CLAUDE.md): outcomes in the proposal and on the issue, `zebra-feedback.sh` → build →
merge → deploy green → fresh Claude subagent writes `claude.json` → `zebra-outcome-review.sh run`
→ exit 0: post the table, file follow-ups for `followups`; exit 2: blocked, tell the user, poll
`status`. `cicd-manager` returns `OUTCOME REVIEW PENDING` to its caller instead of running it.

## Configuration

`ZEBRA_SOURCE_ROOT` (optional); script env `ZEBRA_REVIEW_MODEL` (default `sonnet`),
`ZEBRA_FEEDBACK_CONTAINER` (`zebra-web`), `ZEBRA_URL` (task links).

## Open questions / risks

- The model may return malformed JSON. It counts as disputed, so the failure mode is a human
  task, not a false pass.
- Claude's side has no rebuttal round inside the workflow; the human sees both positions.
- Cost: up to two Sonnet `llm_agent` passes per feature. Both set `answer_on_budget`, so a review
  that spends its tool turns (12, then 6) still answers instead of failing (#191; the first real
  run, of #190, failed after 8 turns).
- In prod `/app` holds only the packages, `pyproject.toml` and `version.json`, so Zebra judges
  docs and script outcomes from the diff alone.
- A diff over 60000 chars is truncated; Zebra reads the source for the rest.
