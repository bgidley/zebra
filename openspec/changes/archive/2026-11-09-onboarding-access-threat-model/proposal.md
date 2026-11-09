## Why

The onboarding epic (#275) lets anonymous visitors build a Zebra in their own OCI tenancy through
a wizard on any host Zebra. Before any build slice, the session model, the access grant and the
threat model must be agreed and reviewed (#276, #278).

## What Changes

- Add `specs/onboarding-design.md`: anonymous resumable session model, access options A/B/C, the
  compartment-scoped policy text with tenancy-level grants shown separately, the callback token
  protocol, the threat model (assets, six attackers, mitigations, residual risks).
- Index it in `specs/AGENTS.md` and reference it from `specs/zebra-as-is.md`.
- Docs only: no code, no runtime change.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A threat model (assets, attackers T1-T6, mitigations) is written and posted on #278 | `specs/onboarding-design.md` section 5, note on #278 |
| O2 | The policy text is scoped to one compartment, with the two tenancy-level grants shown separately | design doc section 3 |
| O3 | The session model and callback protocol are specified well enough to build S1-S4 | design doc sections 2 and 4 |
| O4 | The design is indexed in `specs/AGENTS.md` and linked from `zebra-as-is.md` | both files |

## Impact

Docs only. Superseded wording in the original #276 (`OnboardingSession` table, authenticated user)
is flagged in the design doc, not rewritten on the issue.
