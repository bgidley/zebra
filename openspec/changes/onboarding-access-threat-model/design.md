## Context

See `specs/onboarding-design.md` (the design of record).

## Decisions

- No accounts and no session table: one engine process per visitor, signed resume token.
- Access: Resource Manager stack by default (host holds nothing), instance principals for runtime,
  scoped API key only as a policy-text fallback with no key upload in v1.
- Tenancy-level grants (budgets, quotas, dynamic group) are shown apart from the one-compartment
  policy.
