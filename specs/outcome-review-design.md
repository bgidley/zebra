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
{status: agreed|disputed|ruled, rows, disputed, followups, table_markdown, summary_markdown,
dispute_notes, ruling_form, briefs?, ruling?, unruled?}`. `table_markdown` (posted on the issue) has
both sides' evidence, and a Ruling column once ruled; `summary_markdown` has id, outcome text,
verdicts and agreed only; `dispute_notes` is a markdown section per disputed outcome with the
outcome text and each side's evidence (#215). Since #295 `ruling_form` is the JSON Schema the
ruling task renders, `briefs` is `{id: {crux, zebra, claude, settle}}`, a ruled row has `ruling` /
`ruling_note`, and `unruled` lists disputed outcomes the human did not pick a verdict for.

## Interfaces

| Piece | What it is |
|---|---|
| `## Outcomes` in `proposal.md` | Required by `openspec/config.yaml`: `#`, outcome, how we'll know. Posted on the issue |
| `scripts/zebra-feedback.sh` | Now reviews the proposed outcomes at the start (advisory, always exits 0) |
| `zebra_source` action | `operation: read` (line range, 12000-char cap) / `search` (regex, glob, 50 hits) / `list` (one directory level: subdirectories with file counts, files with sizes; or with a `glob`, matching file paths; 200 entries) (#211). A read of a missing path fails with up to 5 nearest existing paths (same file name first, then `difflib` close matches) and a hint to list or search; a directory read fails with its listing; a path under an allowlisted entry that is not deployed names the entries that are. Every failure ends with the list/search hint. Suggestions and listings come from the allowed file walk, so hidden entries are never named. Root `ZEBRA_SOURCE_ROOT` or the checkout above the installed `zebra_tasks` (`/app` in prod). Allowlist: the four packages, `specs`, `openspec`, `docs`, `scripts`, `deploy`, `pyproject.toml`, `version.json`, top-level `*.md`. Refuses dot-entries, `*.sqlite3`/`*.db`/keys, `tmp/`, `staticfiles/`, `fixtures/`, symlinks and anything resolving outside the root |
| *List Zebra Source*, *Read Zebra Source*, *Search Zebra Source* | Tool-only workflows around `zebra_source` for `llm_agent`; their descriptions name the deployed top-level entries (#211) |
| `compare_outcome_reviews` action | Parses both reviews (dict, list or fenced JSON), lines them up per outcome id, routes `agreed` / `disputed`. Missing, unknown or garbled verdicts are disputed, and every id in the outcomes table (`outcomes_key`) is compared, so an outcome neither reviewer judged is disputed too (#191). `reconsidered_key` overlays Zebra's second verdicts; `ruling_key` records the human ruling (`ruled`, per outcome via `record_ruling()`, #295); `final` records without routing. Always writes `ruling_form` (`ruling_form()`) and carries `briefs` forward |
| `brief_outcome_disputes` action | #295: one low-tier `complete_json` call over both sides' evidence for the disputed outcomes; `parse_briefs()` keeps a crux, positions and what would settle it per outcome, dropping fields that take a side (`TAKES_A_SIDE`); rebuilds `ruling_form`. Never fails (no LLM, error or junk → first-sentence fallback) |
| *Outcome Review* workflow | System, tool-only (required `inputs`), `result_key: review_result` |
| `zebra_agent.direct_run` | `run_named_workflow()` creates and starts a named workflow from inputs (required inputs checked); `workflow_status()` → `complete` / `awaiting_input` / `failed` / `running` |
| `manage.py run_workflow` | `<name> --input-file - [--model medium]` or `--status <process_id>`; prints the status JSON, exits 1 on failure |
| `scripts/zebra-outcome-review.sh` | `run <N> <title> outcomes.md claude.json <base> [head]` builds the inputs on the host (diff capped at 60000 chars; deployed hash from `/app/version.json`) and runs the workflow in `zebra-web`; `status <process_id>` polls. Exit 0 complete, 2 waiting on a human, 1 failed. Tested with a fake `podman` in `zebra-agent/tests/test_outcome_review_script.py` (#192) |

## Control flow

```
zebra_review (llm_agent + source tools, JSON, blind)
  → compare ── agreed ──────────────────────────────→ finish (final)
            └─ disputed → zebra_reconsider (sees Claude's notes for disputed outcomes only)
                          → compare_again ── agreed ─→ finish
                                         └─ disputed → brief_disputes → human_ruling (auto: false)
                                                                          → record_ruling
```

The human task's form is generated (`schema: "{{review_result.ruling_form}}"`, v6, #295): agreed
outcomes in one line, then per disputed outcome the outcome, the crux (labelled a model summary),
both verdicts with one-sentence positions and what would settle it, followed by a required
met / partial / missed pick labelled with who said which and an optional note; the full evidence is
the last panel. Reviewer and brief text is made inert (`{{` broken) because the form resolves
templates. Earlier steps' raw output is hidden (`show_prior_outputs: false`, #215). It
appears on `/tasks/`. The process runs with a `run_id`, outside the Agent Main Loop (no
selection, metrics or memory).

Session side (CLAUDE.md): outcomes in the proposal and on the issue, `zebra-feedback.sh` → build →
merge → deploy green → fresh Claude subagent writes `claude.json` → `zebra-outcome-review.sh run`
→ exit 0: post the table, file follow-ups for `followups`; exit 2: blocked, tell the user, poll
`status`. `cicd-manager` returns `OUTCOME REVIEW PENDING` to its caller instead of running it.

## Configuration

`ZEBRA_SOURCE_ROOT` (optional); script env `ZEBRA_REVIEW_MODEL` (default `medium`),
`ZEBRA_FEEDBACK_CONTAINER` (`zebra-web`), `ZEBRA_URL` (task links).

## Open questions / risks

- The model may return malformed JSON. It counts as disputed, so the failure mode is a human
  task, not a false pass.
- Claude's side has no rebuttal round inside the workflow; the human sees both positions.
- Cost: up to two medium-tier `llm_agent` passes per feature. Both set `answer_on_budget`, so a review
  that spends its tool turns still answers instead of failing (#191; the first real
  run, of #190, failed after 8 turns). Since #285 the budget is 8, then 5: the #236 review spent
  12 turns ($1.42, 594k input tokens) mostly on a broken range read (dream copy of *Read Zebra
  Source*), empty brace globs and searching for tests the diff already held.
- A `change_map` input (from the script: every changed file with +/- counts, then the test
  functions added or changed, capped at 8000 chars) comes before the diff in the prompt, so the
  agent starts from the tests and still sees every file when the diff is truncated (#285).
- Since #212 the image also ships `specs/`, `docs/`, `openspec/`, `scripts/`, `deploy/` and the
  root `*.md` files, so Zebra can read the docs and scripts an outcome names. Before that every
  failed source read on prod (18 of 171) was for one of these paths.
- A diff over 60000 chars is truncated; Zebra reads the source for the rest.
