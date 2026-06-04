---
name: f4-f5-identity-auth
description: Single-user identity (F4) and web authentication via passkeys (F5)
metadata:
  type: feature-spec
  issues: "#4, #5"
  requirements: REQ-USR-001, REQ-NFR-007
  status: implemented
---

# F4 + F5: Single-User Identity & Web Authentication

**GitLab issues**: #4, #5  
**Requirements**: REQ-USR-001, REQ-NFR-007  
**Status**: Implemented

## Goal & scope

**F4**: First-run setup flow captures user's display name and generates a local identity. Stored in `SystemStateModel`. Every process/run is stamped with this identity.

**F5**: Django session authentication via **passkeys** (WebAuthn / py_webauthn) on all web endpoints. Unauthenticated requests redirect to login; no-user requests redirect to setup.

Out of scope: multi-user, SSO backends, passkey management UI (no delete/rename of registered passkeys).

## Data model changes

**`SystemStateModel`** gains F4 identity fields (migration after `0008`):
- `user_display_name` (varchar, blank=True, default="")
- `user_identity_id` (varchar 255, blank=True, default="") — stable UUID generated at setup

**`WebAuthnCredential`** table (new):
- `credential_id` (bytes, unique)
- `public_key` (bytes)
- `sign_count` (int)
- `user` (FK → `auth.User`)

Django's built-in `auth_user` table holds the single user account.

**Process stamping**: when a process is created, the agent engine injects `__user_display_name__` and `__user_identity_id__` into `process.properties` from `SystemStateModel`.

## First-run setup flow

1. `SetupRedirectMiddleware` — on every request, reads `SystemStateModel` (pk=1). If `user_display_name` is empty, redirects to `/setup/` (exempt: `/api/health/`, `/api/metrics/`, `/setup/`, `/login/`).
2. Setup page (`GET /setup/`) — form for display name + passkey registration.
3. `POST /setup/` — saves `user_display_name` + `user_identity_id` (new UUID) to `SystemStateModel`; creates a Django `User` account; stores the WebAuthn credential.

Two overlapping middleware layers handle different conditions:
- `SetupRedirectMiddleware` → redirects when no identity exists
- `LoginRequiredMiddleware` → redirects when identity exists but user not authenticated

## Authentication

**Mechanism**: Passkey-only (no password fallback in the web UI).

**Endpoints**:
- `GET /login/` — passkey challenge page
- `POST /api/auth/passkey/begin/` — returns WebAuthn assertion challenge (stored in session)
- `POST /api/auth/passkey/complete/` — validates assertion via `py_webauthn`, calls `django.contrib.auth.login()`

**Settings**: `AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]`. Session auth standard Django behaviour.

**Challenge store**: WebAuthn challenges are stored in the Django session (in-memory during the challenge/response round trip). No persistent challenge table — if the server restarts between `begin` and `complete`, the challenge is lost (acceptable for single-user local use).

## Middleware stack

```
SetupRedirectMiddleware
  └─ LoginRequiredMiddleware
       └─ CurrentUserMiddleware   (F6 — binds user_id ContextVar)
```

`_ALWAYS_ALLOWED` paths (bypass all three): `/api/health/`, `/api/metrics/`, `/api/kill-switch/`, `/setup/`, `/login/`, `/api/auth/`.

## Open questions / risks

- **No passkey management UI** — users cannot delete or rename registered passkeys; recovery if device is lost requires DB intervention.
- **Two overlapping middleware layers** can produce confusing redirect loops if the always-allowed list diverges between them.
- **Challenge store is in-session** — stateless deployments (multiple workers) would need a shared challenge store.
- **Single Django User** — the F6 multi-user path will require aligning `SystemStateModel` identity with `auth.User.pk`.
