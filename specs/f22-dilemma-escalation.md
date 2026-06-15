# F22: Dilemma Escalation (REQ-ETH-005)

## Goal & scope

When the values-informed ethics gate finds that an action is **Kantian-permissible**
but the user's values are in **genuine conflict** (value-vs-value, or a reasonable
Kantian view in real tension with a personal value), the agent **pauses and escalates**
to the human instead of silently applying the precedence rule. The escalation UI shows
both sides and the agent's recommendation; the human's decision drives the route and is
recorded to the ethics audit trail.

GitLab issue: [#22](https://gitlab.com/gidley/zebra/-/issues/22).

Explicitly **not** a dilemma (no escalation):
- Clear alignment with all values → just proceed.
- A stated **deal-breaker** violation or a **Kantian failure** → decisive reject; the
  user pre-declared a "no", there is nothing to deliberate.

Out of scope (deferred): persisting dilemma *patterns* to `PersonalKnowledgeStore` under
a `dilemma_resolutions` category (needs a knowledge-taxonomy change). The resolution is
recorded to the existing ethics audit trail (F20), satisfying "the resolution is recorded".

## Data model changes

No new tables or store interfaces.

- `EthicsGateAction` combined (values) output gains a `dilemma` object:
  `{detected, summary, sides[{position, values[], reasoning}], recommendation,
  recommendation_reasoning}`. When a dilemma is detected it also writes a flat
  `dilemma_display` process property (human-readable both-sides text) so the human-task
  form can render it via a simple `{{dilemma_display}}` default.
- `record_dilemma_resolution` stores a `dilemma_resolution` process property
  `{decision, note, route}` and appends an `EthicsAuditEntry` with
  `check_type="dilemma_resolution"`.

## API / interface changes

- `EthicsGateAction` adds the routing verdict **`escalate`** (in addition to
  `proceed` / `reject`). Only emitted when a values profile is loaded *and* the LLM flags
  a genuine dilemma on a Kantian-permissible action. With no profile, `escalate` is never
  emitted — behaviour is unchanged (backward compatible).
- New action `record_dilemma_resolution`
  (`zebra_tasks.agent.record_dilemma_resolution:RecordDilemmaResolutionAction`), registered
  as a `zebra.tasks` entry point. Reads the human resolution task output, records it, and
  re-emits the decision as `next_route` (`proceed`/`reject`).

## Control flow

`agent_main_loop.yaml` (version 5): the plan-review gate now receives
`user_id: "{{__user_id__}}"` (activating values-informed evaluation, F19, in the loop for
the first time) and gains an escalation branch:

```
ethics_plan_review ─proceed──────────────────────────────────→ execute_workflow
                   ─reject───────────────────────────────────→ ethics_rejection
                   ─escalate─→ ethics_dilemma_resolution (human, auto:false)
                                        │
                                 record_dilemma_resolution ─proceed─→ execute_workflow
                                                            ─reject──→ ethics_rejection
```

`ethics_dilemma_resolution` is a convention-based human task: a read-only multiline
`dilemma` field (defaulted from `{{dilemma_display}}`) presenting both sides, plus a
`decision` enum (`proceed` / `decline`) and an optional `note`. The workflow pauses there
until the human submits; the existing human-task UI renders it.

Escalation is wired at the **plan-review** gate only — the point where a concrete action
and its values trade-offs are clearest and where "proceed" cleanly means "execute". The
input gate retains proceed/reject semantics.

## Configuration

None. The plan-review gate uses the workflow/process default model.

## Open questions / risks

- The LLM decides what counts as a genuine dilemma vs a decisive deal-breaker; the prompt
  steers this but it is a judgment call. Fail-safe: an unparseable gate response falls open
  to `proceed` (existing behaviour); the resolution defaults to `proceed` if the human task
  output is somehow missing (never stuck).
- Personal-knowledge persistence of dilemma patterns (`dilemma_resolutions`) is deferred to
  a follow-up that extends `KNOWLEDGE_CATEGORIES`.
- Escalation is not yet wired at the input gate; goal-level dilemmas surface at plan review.
