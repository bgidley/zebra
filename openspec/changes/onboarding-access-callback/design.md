## Context

Built on the #276 shell (one *Onboarding* process per anonymous visitor, no accounts, no
secrets). Full design and threat model: `specs/onboarding-design.md` (§3 policy, §4 protocol,
§5 threat model, §6b as built).

## Decisions

- **Inline, not a child workflow.** The access step lives in `onboarding.yaml` (new tasks
  `access_policy`, `await_instance`), so the wizard still reads one process by id and
  `ONBOARDING_WORKFLOWS` stays `{"Onboarding"}`. A child would need cross-process reads from an
  anonymous view (stores fail open).
- **Panels by task property.** `onboarding_panel` names extra content (`access`, `policy`,
  `provision`, `await`) rendered by `partials/panel.html`; the generic form stays generic.
- **Token on the provision step**, shown once with `no-store`; provision cannot complete before a
  token exists, because the stack variable must hold it before Apply.
- **Proof before claim.** Lookup, liveness and "is the session waiting" are checked before any
  fetch (a dead token fetches nothing). The used flag is set by compare-and-set under the process
  lock after the proof, so concurrent callbacks complete once and a failed proof costs nothing.
- **Pinned IP.** All DNS answers must be public; the GET goes to the checked IP with `Host` and
  SNI set to the name (certificate verified against it). Raw bytes are capped (identity encoding)
  so a compressed body cannot expand past the cap.
- **One 410** for unknown, used, rotated and expired tokens: no oracle for token state.
- **Policy `quota`**: OCI's resource type is `quota` (as in #279's guardrails doc); the design
  text is corrected and a test keeps the code and design identical.

## Risks

- The stack has no `onboarding_token` variable yet and names its compartment `zebra`; #279 S5.
- RUNNING scan on a cache miss is linear in live sessions (capped at 200).
