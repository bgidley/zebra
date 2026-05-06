## Why

When multiple deployments are running it is hard to confirm which version is live.
A visible git-derived version stamp in the UI footer, with a click-to-expand recent-changes panel,
lets developers and operators verify at a glance that the right code is deployed.

## What Changes

- A persistent footer is added to the zebra-agent-web Django templates showing the current git commit
  short hash and date.
- The version string is derived at server start-up from `git describe` / `git log` and exposed via
  a lightweight Django view (`/api/version/`).
- Clicking the footer opens an overlay/panel showing the last ~10 commits from `master` (short hash,
  date, subject line).

## Capabilities

### New Capabilities

- `version-footer`: Version display footer — server-side git metadata endpoint + client-side footer
  component that fetches and renders it; click-to-expand recent-commits panel.

### Modified Capabilities

_(none — no existing spec requirements change)_

## Non-goals

- No semantic versioning / release tags.
- No real-time polling; version is fetched once on page load.
- No diff viewer or full commit details.

## Impact

- **zebra-agent-web**: new URL route, Django view, template fragment, static JS fetch.
- **Deployment**: git history must be available in the production container / VM (already the case
  on the Oracle VM runner).
- No database changes. No API breaking changes.
