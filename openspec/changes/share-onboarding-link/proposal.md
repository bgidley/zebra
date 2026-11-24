## Why

Signed-in users of a Zebra hosting the wizard have no way to point friends at `/onboarding/` (#330).

## What Changes

- Main-navigation entry "Invite a friend" and page `/invite/`: the public onboarding https link, a Share button (`navigator.share`, shown only where available) and a Copy button, plus a short message.
- New setting `PUBLIC_BASE_URL` (`ZEBRA_PUBLIC_BASE_URL`); falls back to the first https `CSRF_TRUSTED_ORIGINS` entry. The link is never built from the Host header. With no https origin the page says how to set it.
- Entry and page absent (404) while onboarding is off (page: env AND owner switch; nav entry: env switch, like the owner's Onboarding link).

## Non-goals

Referral tracking or rewards, inviter identity in the link, an editable message.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A signed-in user reaches the share panel from the main navigation and gets a copyable https link | e2e test; screenshot at phone and desktop width |
| O2 | The link opens the wizard for an anonymous visitor with no login | e2e test |
| O3 | With onboarding disabled the entry and panel are absent (404) | unit tests (env off, owner switch off, nav) |
| O4 | The link contains no user identity and uses the configured public origin, never the Host header | unit tests (hostile Host header, userinfo origin, http origin) |
