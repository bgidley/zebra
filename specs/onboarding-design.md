# Onboarding: sessions, access grant and threat model (#276, #278)

Part of epic #275. Slice S0 (`onboarding-access-threat-model`) is docs only. It fixes the design
the build slices S1-S4 implement and the threat model they are reviewed against.

## 1. Goal & scope

A visitor who wants their own Zebra is walked through a wizard on a host Zebra: signup, access,
provision, verify, commons, contribute. The new Zebra is built in the **visitor's own OCI tenancy**.

- #276: the wizard shell and its anonymous, resumable sessions.
- #278: how the visitor grants access, with the host able to do as little as possible.
- Not here: the provisioning content (#279, #283), updates, the Commons step itself.
- Constraints: Oracle DB, arm64, inside OCI Always Free (2 OCPU / 12 GB Arm), default region
  `uk-london-1`, the GitHub mirror is the contribution target.

## 2. Session model (#276)

Any Zebra can host the wizard, including one with real users and data, so the wizard is safe there
by construction: **no accounts, no tables, no secrets.**

- **State is one engine process per visitor**: the `onboarding` workflow
  (`zebra-agent/workflows/onboarding/`). Steps are tasks. User steps are `auto: false` forms. Waits
  on the new instance are `external: onboarding_callback`, which `zebra.forms.is_human_task()` keeps
  out of the owner's inbox. There is no `OnboardingSession` table; the process properties are the
  state (this supersedes the table in the original #276 body).
- **Resume token**: a `django.core.signing` token `{p: process_id, n: nonce}` in an HttpOnly,
  Secure, SameSite=Lax cookie and in a "resume link". The process holds only
  `__onboarding_nonce_sha256__`. Resume checks the signature, loads the process by id, compares the
  hash. "Forget me" rotates the nonce. Expiry 30 days idle.
- **Auth fit**: `/onboarding/*` views are `@login_not_required` and exempt from
  `SetupRedirectMiddleware` and `SetupRequiredMiddleware`. With no request user the stores **fail
  open** (`get_current_user_id()` is None, queries unfiltered), so wizard views call only
  `get_process(id)` and that process's tasks, never list queries (a test asserts it). Processes get
  `user_id` NULL and never show in a user's activity. No path calls `User.objects.create` or a
  passkey view (a source-scan test enforces it).
- **Launch**: `zebra_tasks.launch.create_library_process(engine, defn, entry="onboarding")` (new
  `LAUNCH_ENTRIES` member), then started at once (a CREATED process would be picked up as a queued
  goal). Allowlist `ONBOARDING_WORKFLOWS = {"onboarding"}` plus later step children (e.g.
  `onboarding_access`). Launch is refused unless the definition's provenance is built-in, so a
  dream copy or Commons import cannot shadow it.
- **Cost**: v1 steps make no LLM calls. Hard guards anyway: process property `__cost_cap_usd__`
  checked in `zebra_tasks.llm.client._Recorded` before each call (default
  `ONBOARDING_SESSION_COST_CAP_USD=0.05`), and `ONBOARDING_DAILY_COST_CAP_USD=1.00` summed from the
  spend ledger. The kill switch halts the wizard.
- **Rate limit** (Django cache, LocMem, single web process, keyed by IP): 5 new sessions/hour,
  60 requests/minute, 200 live sessions overall. The daemon tick fails sessions idle over 30 days.
- **Switch**: `SystemStateModel.onboarding_enabled` (owner-only toggle) ANDed with env
  `ZEBRA_ONBOARDING_ENABLED` (default false). Off means `/onboarding/` 404s and nothing is created.

## 3. Access grant options (#278)

| | Option | Host holds | Use |
|--|--------|-----------|-----|
| A | **OCI Resource Manager stack** ("Deploy to Oracle Cloud" link to a published Terraform stack, `zipUrl` from #283). The user clicks Apply in their own tenancy. | Nothing | **Default, provisioning** |
| B | **Scoped API key**: dedicated IAM user + group with a one-compartment policy, user uploads a key, host runs Terraform/SDK. | A secret, in memory, once | Fallback only. **v1 uploads no key**: it renders the generated policy text and the user applies the stack themselves. |
| C | **Instance principals / dynamic group** for what the new instance does later (own images, own Vault secrets). | Nothing | **Runtime** |

Recommendation: A for provisioning, C for runtime, B only for users who cannot use Resource
Manager, with the policy shown before they create anything.

Facts that shape this (from the #278 review):

- Resource Manager jobs run as the **applying user**. Option A needs no policy from us; the
  stack-own-permissions policy below applies to B only.
- **Applying user must be a tenancy admin** if the stack creates the tenancy-level pieces: the
  dynamic group and policy for C, and the budgets and quotas of #279 (they live at tenancy/root
  level). The wizard states this before the Apply link. A non-admin gets the policy text to hand to
  their admin, or skips budgets and quotas and is told to create them (weaker).
- "Deploy to OCI" needs a **publicly reachable `zipUrl`** (built by the #283 pipeline, with a
  published checksum). The zip holds no secrets.
- The stack provisions **Always Free shapes only** and only inside its compartment.

### Policy text (B, and the admin's copy for C)

The wizard prints this exact text with `<name>` filled in. **Compartment-scoped part** (one
compartment, `zebra-<name>`, no `manage all-resources`):

```
Allow group zebra-<name>-admins to manage instance-family in compartment zebra-<name>
Allow group zebra-<name>-admins to manage virtual-network-family in compartment zebra-<name>
Allow group zebra-<name>-admins to manage autonomous-database-family in compartment zebra-<name>
Allow group zebra-<name>-admins to manage vaults in compartment zebra-<name>
Allow group zebra-<name>-admins to manage keys in compartment zebra-<name>
Allow group zebra-<name>-admins to manage secret-family in compartment zebra-<name>
Allow group zebra-<name>-admins to manage object-family in compartment zebra-<name>
Allow group zebra-<name>-admins to read compartments in compartment zebra-<name>
```

**Tenancy-level part**, shown separately and optional, because it breaks the one-compartment
claim. Only for a user who accepts both grants (budgets and quotas for #279):

```
Allow group zebra-<name>-admins to manage usage-budgets in tenancy
Allow group zebra-<name>-admins to manage quotas in tenancy
```

**Runtime (option C)**, tenancy-level objects an admin creates; the instance gets read only:

```
Dynamic group zebra-<name>-instances:
  Any {instance.compartment.id = '<compartment ocid>'}
Allow dynamic-group zebra-<name>-instances to read secret-family in compartment zebra-<name>
Allow dynamic-group zebra-<name>-instances to read object-family in compartment zebra-<name>
```

The last screen of the access step is **revoke**: delete the group and policy (B), delete the
dynamic group, destroy the stack, remove the API key. It is reachable from every terminal state.

## 4. Callback protocol (#278, #279)

1. At the provision step the host makes `cb` (32 random bytes, base64url) and stores `sha256(cb)`,
   `expires = now + 1h`, `used = false` in process properties. It shows `cb` once; the user pastes
   it into the stack variable `onboarding_token` (it stays in their tenancy).
2. On first boot the instance calls `POST https://host/onboarding/callback/` with
   `{token, instance_url, commons_fingerprint?, version}`. CSRF-exempt, rate limited; lookup is by
   token hash (cache plus a scan of RUNNING onboarding processes only).
3. The host checks hash, expiry and unused flag, then **verifies control**: `GET
   instance_url/.well-known/zebra-onboarding` must return `sha256(cb)`. The fetch is https, port
   443, to a resolved public IP only, no redirects, 5 s timeout, 4 KB cap.
4. On success it marks the token used, completes the `await_instance` external task with non-secret
   outputs, and the process moves to verify (`/api/health`, `/api/version`). Any failure leaves the
   token unused until it expires. A new token rotates the old one. A replayed or expired token gets
   410 and changes nothing. A manual-paste fallback of the instance URL exists, with the same
   challenge check.

## 5. Threat model

**Assets**: the visitor's OCI tenancy; host owner data and accounts; the host's LLM budget; session
integrity (whose instance is whose); the new instance's secrets (OpenRouter key, Commons keys),
which never reach the host.

| Attacker | Wants | Mitigations |
|----------|-------|-------------|
| **T1** anonymous internet visitor or bot | spam sessions, burn LLM budget, reach host data, create accounts | Per-IP rate limits and a global session cap; $0 LLM in v1 plus hard session and daily caps; owner-only enable, default off; no user creation (source-scan test); no list queries (test); workflow allowlist with built-in provenance; kill switch |
| **T2** steals a session cookie or resume link | impersonate the visitor | The session holds no secret or tenancy power; the worst case is seeing progress or editing non-secret answers. Nonce rotation ("forget me"); HttpOnly, Secure, SameSite=Lax; 30-day expiry; signed token, hash compare |
| **T3** compromises the host | use the visitor's tenancy, read their data | Option A: the host holds nothing usable against a tenancy (outcome O1 of #278). B would hold a key, so v1 uploads none; any later B keeps the key in memory only, uses it once, then shows revoke steps. OpenRouter and Commons keys are generated on the new instance. A stolen callback token is useless after use or 1 h and proves nothing without control of the instance URL |
| **T4** malicious or confused user (wrong key, wrong URL) | trick the host into fetching or storing something | Forms never accept keys or private material (pattern-checked; private-key PEM rejected); instance URLs are verified by challenge, not trusted; SSRF guards on the fetch |
| **T5** network attacker on the callback | read, replay or forge the call | TLS only; one-time, 1-hour, hashed token; control-proof fetch; SSRF guards; replay gets 410 |
| **T6** malicious published stack or zip (supply chain) | run code in the visitor's tenancy | Zip built by the #283 pipeline with a published checksum; the wizard shows version and hash; Always Free shapes only, resources only in its compartment; the zip is public and reviewable |

Residual risks (accepted or tracked):

- LocMem rate limits reset on restart (acceptable on one host).
- IP-only limits are weak behind NAT or CGNAT.
- The RUNNING scan in the token lookup does not scale; fine at the 200-session cap.
- Stores fail open: a later wizard view that adds a list query would leak; the test guards it.
- Resource Manager variables may appear in the user's own job logs (the token is one-time and 1 h).
- Option A needs a tenancy admin for budgets, quotas and the dynamic group; B's tenancy grants widen
  the blast radius for those who accept them.

## 6. Slices and interfaces

S1 wizard shell (#276), S2 guardrails (#276), S3 access step (#278), S4 callback (#278/#279). Each
has its own OpenSpec change. New settings: `ONBOARDING_ENABLED` (env default false, ANDed with the
owner toggle), `ONBOARDING_SESSION_COST_CAP_USD`, `ONBOARDING_DAILY_COST_CAP_USD`,
`ONBOARDING_STACK_ZIP_URL` (stubbed until #283). New endpoints: `/onboarding/*`,
`POST /onboarding/callback/`, `manage.py onboarding_call_home` (instance side, wired in #279).

## 7. Open questions

- #283 `zipUrl` does not exist yet; S3 stubs it.
- Whether B ever uploads a key (v1: no). Revisit only with a concrete user who cannot use A.
- Update path: does a later release update need any stored credential? Tracked in the update issue.
