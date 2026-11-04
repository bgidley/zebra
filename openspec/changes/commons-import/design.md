## Context

S0 (#245) put every start of a library workflow behind `zebra_tasks.launch.create_library_process`
→ `check_launch` (a no-op) and added strict `unsafe_reason`. S2b (#229) gave the signed export
file, `verify_export`, `save(writer="adopt")`, the owner-governed `sharing` trust domain and
`commons_pii_scan`. S3 joins them into a judged import and enforces `commons.supervised`.

## Goals / Non-Goals

**Goals:** judged import of a signed file, with every gate able to reject and record why; a gym
that never runs anything a human has not seen unless it is `always_reversible`; supervised
pre-run approval for imported workflows from every entry point; owner-only approvals.

**Non-Goals:** relays, offers, attestations, reputation and import scores (S4+); market (S7);
sync between own devices (S3b). `ATTEST` events are not published: the result is recorded on the
import process (`commons_import_result`) only.

## Decisions

1. **The pipeline is a system workflow** (`commons_import.yaml`, tagged `system`, tool-only via
   required `export_file` input) so it is protected, never optimized, exported or selected. Input:
   the export file text. Steps and routes:
   `judge` (proceed/reject) → `pii_scan` (clean/rejected) → `ethics` (proceed/reject/escalate) →
   `gym` (passed/rejected/escalate) → `trust` (proceed/approve) → `adopt` (adopted/refused) →
   `record_adopted`. `approve`, `escalate` and ethics `escalate` go to `review` →
   `owner_approval` (owner-only human task, `decision: adopt|reject`) → `adopt_approved`. Each
   rejecting route has its own `commons_record_import` task with a fixed stage and a reason
   template, so the record always names the gate.
2. **Judge** (`commons_judge_import`) re-runs `verify_export` with the held certs/revokes from the
   `__commons__` service in `context.extras` (the web injects it; absent → no held revokes), loads
   the YAML as a definition, requires every action registered, refuses a local name taken by a
   different workflow, and builds `offer`: name, local name, yaml, commons block, hash, publisher
   key + display name, golden tasks, and the action list with hints. It also refuses while the
   Commons is stopped.
3. **Gym import mode** is a third plan mode beside `gate` and `on_demand`, selected by
   `mode: import` + `offer`. Only a `candidate` variant runs (there is no local version to
   regress against). Golden tasks: the offer's (ids `offer-<hash12>-<n>`, workflow = offer name)
   plus `library.list_golden_tasks(offer.name)`, capped by `max_tasks_per_workflow`. Those dicts are
   kept in the plan so `_finish` can judge them. Decision: every run scored and mean ≥ `pass_score`
   (0.6) → `passed`; scored below → `rejected`; strict-unsafe, no runnable golden tasks, no judge,
   over the cap, an unscored run or a gym error → `escalate`. Import mode never calls
   `save_workflow_file` whatever `promote` says.
4. **Supervised use is a generated wrapper**, not a change to the imported YAML or to callers.
   `check_launch` reads the library's block for the definition's name; if `supervised` it returns
   `SupervisedLaunch(workflow, actions)` (and raises `LaunchRefused` while the Commons is
   stopped). `create_library_process` saves the real definition and creates a process of
   `supervised_run_definition(real)` instead: id `s:<real id>`, name `Supervised run: <name>`,
   tagged `system`, same `result_key`; properties = the caller's plus `__supervised_launch__`
   (definition id, name, actions, entry, original properties) and a markdown `supervised_summary`.
   Its tasks: `approve_run` (owner-only, `decision: run|reject`) → `apply_decision`
   (`commons_supervised_run`). On `run` it starts the real workflow as its child (a direct
   `engine.create_process`, allowlisted: approved at the choke point), suspends, and on resume
   copies the child's non-`__` properties, `__output__` and cost, records the run with the library
   and succeeds or fails like the child. Anything but `run` fails with `__supervised_rejected__`.
   Every caller already starts and suspends on (or watches) the process it gets back, so goals,
   routines, direct runs, sub-workflows and tools all park on the approval.
5. **Failover**: `execute_goal_workflow` sees a wrapper that failed with `__supervised_rejected__`,
   adds the workflow to `__excluded_workflows__` and returns `next_route: supervision_rejected`;
   the Agent Main Loop (v19) routes that back to `select_workflow`, which leaves excluded
   workflows out (and ignores an excluded `requested_workflow`). Its normal routing to
   `assess_stuck` becomes a nameless `route_name` routing, which fires when no route is set.
6. **Supervision state** is local bookkeeping: the approved-successful-run count lives in
   `<library>/.lineage/supervision.json` keyed by content hash (never in the exported block).
   `record_supervised_run` clears `supervised` in place in the current file at `SUPERVISED_RUNS`
   (3); `clear_supervision(name)` is the owner's clear; `resupervise_adopted()` (emergency
   override) sets it again on every adopted workflow and resets the counts. Only the flag changes,
   so the hash and definition id do not.
7. **Owner only**: a task definition property `owner_only: true` makes the web form and
   `POST /api/tasks/<id>/complete/` refuse (403) anyone but the Commons owner
   (`resolve_commons_owner`).
8. **Stop**: `__commons__.stop_reason()` (web: Commons off or kill switch on) is checked by the
   judge, `commons_adopt`, `check_launch` for supervised workflows and `commons_supervised_run`
   before it starts the child.

## Risks / Trade-offs

- A workflow can still reach a supervised workflow's *content* by inlining it in a `subworkflow`
  under another name; that content is then part of an already supervised (or local) workflow.
- Without a held revoke list (CLI without the web) a revoked device is only caught by its chain.
- Golden tasks are only as good as the publisher's; the gym is a floor, supervision is the guard.
