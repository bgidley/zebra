# Onboarding signup guide and pre-flight (#277)

## Goal & scope
Guide a user with no Oracle Cloud account through signup and take non-secret pre-flight answers. Guidance and shape checks only; no OCI calls. Part of epic #275; the wizard shell (#276) and real checks (#279) come later. GitLab #277.

## Data model
`OnboardingSignupModel` (`zebra_onboarding_signup`, migration 0037): `user_id` (unique), `data` JSON `{tenancy_ocid, region, done[], payg: none|pending|active}`, `updated_at`. No secrets, ever.

## API / interface
- `GET /onboarding/signup/`: guide plus form, login required.
- `POST /onboarding/signup/confirm/`: 200 saved, 422 rejected. Validators in `api/onboarding_preflight.py` (tenancy `ocid1.tenancy.oc<n>..<id>`, region `area-city-n`, secret shapes refused, non-26ai region warns).
- `scripts/check_onboarding_links.py`: link check of the Oracle URLs.

## Control flow
Ready (next step unlocked) = "account created" and "budget alert understood" ticked. Pay-As-You-Go is self-reported; the page shows "upgrade pending" until the user sets it active. The wizard (#276) should read this row; until it lands there is no "next" link.

## Configuration
`ZEBRA_ONBOARDING_ENABLED` (`ONBOARDING_ENABLED`, default off): 404 when off.

## Content provenance (checked 2026-11-16, Oracle docs)
Confirmed: A1 = 2 OCPU / 12 GB for Always Free tenancies; 200 GB block+boot; two Always Free ADBs at 20 GB; 10 TB/month egress; idle compute reclamation (7 days, p95 CPU/network/memory under 20%); ADB stopped after 7 idle days and possibly deleted after 90 stopped days; 26ai regions include London, not Newport. Marked "needs verification" on the page: the 1-2 day upgrade delay and capacity priority, A1 capacity in London, card hold and trial credit details, sign-up UI steps. The page carries `ONBOARDING_GUIDE_VERSION`; bump it with any text change.

## Open questions
Fallback region if London capacity is poor (page lists Oracle's other 26ai regions); how #276 consumes the stored state.
