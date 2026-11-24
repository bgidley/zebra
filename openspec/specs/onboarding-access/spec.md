# onboarding-access Specification

## Purpose
How a visitor grants a new Zebra access to their own OCI tenancy with the host holding no credential, and how the new instance proves where it is (#278).

## Requirements

### Requirement: Access design documented
The onboarding design SHALL specify the anonymous session model, the access options, the callback
protocol and a threat model covering assets, attackers and mitigations before build slices start.

#### Scenario: Threat model present
- **WHEN** a reviewer opens `specs/onboarding-design.md`
- **THEN** it lists assets, attackers T1-T6 and a mitigation for each

### Requirement: Policy scoped to one compartment
The documented access policy SHALL grant only within one compartment, and SHALL show tenancy-level
grants (budgets, quotas, dynamic group) separately.

#### Scenario: Tenancy-level grants separate
- **WHEN** the policy text is read
- **THEN** the compartment-scoped block contains no `in tenancy` statement and the two tenancy
  statements appear in their own block

### Requirement: Access step without credentials
The access step SHALL offer the published Resource Manager stack and, as a fallback, the
design's least-privilege policy text for an administrator. It SHALL state that the applying user
must be a tenancy administrator for the billing guardrails. No access or provision form SHALL
accept a key, OCID or secret, and the host SHALL store no tenancy credential.

#### Scenario: Stack not published
- **WHEN** `ONBOARDING_STACK_ZIP_URL` is empty or not an https URL
- **THEN** the access step shows no "Deploy to Oracle Cloud" link and says the stack is not
  available yet

#### Scenario: Stack published
- **WHEN** `ONBOARDING_STACK_ZIP_URL` is an https URL
- **THEN** the access step links to Resource Manager's create-stack page with that `zipUrl`

#### Scenario: Policy fallback
- **WHEN** the visitor chooses the policy route with a short name
- **THEN** the wizard shows the compartment block, the two tenancy grants and the runtime grants
  as separate blocks, equal to the design text with that name filled in

### Requirement: Revoke screen
The wizard SHALL offer a revoke screen listing how to remove everything it had the visitor set
up, reachable from every step, every terminal state and without a session.

#### Scenario: Ended session
- **WHEN** a session has ended (failed, expired or forgotten)
- **THEN** the page the visitor sees links to `/onboarding/revoke/`, which returns 200

### Requirement: One-time callback token
The provision step SHALL issue a one-time callback token (32 random bytes, valid 1 hour) shown
once; the session SHALL store only its SHA-256, expiry and a used flag. Issuing a new token SHALL
invalidate the old one. The provision step SHALL not complete before a token exists.

#### Scenario: Rotation
- **WHEN** the visitor makes a new token and the old token is used in a callback
- **THEN** the response is 410 and nothing changes

### Requirement: Instance callback with control proof
`POST /onboarding/callback/` SHALL accept `{token, instance_url, version?, commons_fingerprint?}`
without CSRF, rate limited per IP. Only for a live token of a session waiting on
`await_instance` SHALL the host fetch `<instance_url>/.well-known/zebra-onboarding`, and only if
the body equals the token's SHA-256 SHALL it mark the token used and complete the wait with
non-secret outputs. A replayed, rotated, unknown or expired token SHALL get 410 and change
nothing; a failed proof SHALL get 422 and leave the token unused.

#### Scenario: Success then replay
- **WHEN** the instance calls back with a live token and serves the right hash, then calls again
- **THEN** the first call returns 200 and the session moves to verify; the second returns 410
  and changes nothing

#### Scenario: Concurrent callbacks
- **WHEN** two callbacks with the same token arrive together and both pass the proof
- **THEN** exactly one completes the session

### Requirement: SSRF guards on the control proof
The control-proof fetch SHALL go only to an https origin on port 443 whose every DNS answer is a
global unicast address, pinned to a checked IP with SNI and Host set to the name, with no proxy,
no redirects, a 5 second total limit and a 4 KB body limit.

#### Scenario: Private address
- **WHEN** the instance URL is or resolves to a private, loopback, link-local or CGNAT address
- **THEN** no request is sent and the callback fails

#### Scenario: Redirect, oversized or slow
- **WHEN** the instance answers with a redirect, a body over 4 KB, or nothing within 5 seconds
- **THEN** the redirect is not followed and the callback fails with 422
