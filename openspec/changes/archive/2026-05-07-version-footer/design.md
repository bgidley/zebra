## Context

`zebra-agent-web` is a Django + HTMX + Alpine.js UI. All pages extend `templates/base.html`.
There is no existing version endpoint.

The production runtime is a Docker image built by the CI/CD deploy stage on the Oracle VM.
The image is a two-stage build (`python:3.14-slim`); only explicit source directories are
`COPY`-ed — the `.git` directory is never included in the build context. Therefore `git` is
**not available at runtime** and the version must be captured before the image is built.

## Goals / Non-Goals

**Goals:**
- Expose a `GET /api/version/` JSON endpoint returning git commit hash, date, and recent log.
- Render a small, unobtrusive footer strip at the bottom of every page via `base.html`.
- Clicking the footer opens an Alpine.js panel showing the last 10 commits.

**Non-Goals:**
- Semantic versioning or release tags.
- Real-time polling (one fetch on page load).
- Full diff / commit body display.

## Decisions

### 1 — Bake version at image build time, read file at runtime

**Decision**: The CI/CD deploy step generates `version.json` from `git log` before calling
`podman-compose up -d --build`. The Dockerfile `COPY`s it into the image. The Django app reads
it once in `AppConfig.ready()` and caches the result in a module-level variable.

**Rationale**: The `.git` directory is not in the Docker build context and `git` is not installed
in the runtime image. Generating the file in CI is the correct separation of concerns: CI knows
the commit, the app only needs to read a file.

**Fallback**: If `version.json` is absent (local dev, test runs), the app falls back to
`{"short_hash": "unknown", "date": "", "commits": []}` so the footer still renders.

**Alternative considered**: Pass version info as Docker `--build-arg`. Rejected because the
commit log JSON (multi-line, multi-entry) is difficult to quote correctly as a build arg;
a generated file is unambiguous.

**`version.json` format** (written by CI, read by Django):
```json
{
  "short_hash": "abc1234",
  "date": "2026-05-05",
  "commits": [
    {"hash": "abc1234", "date": "2026-05-05", "subject": "feat: add version footer"}
  ]
}
```

**File location**: `version.json` at the repo root (build context root). Added to `.gitignore`
(generated artefact, not committed). `COPY version.json* /app/` in the Dockerfile (glob so
the build does not fail if the file is absent in non-deploy builds — see note below).

> Note: Docker `COPY` requires at least one matching source; using `version.json*` works only
> if the file is present. We ensure it is always present in the deploy stage. For the builder
> stage we use a conditional copy pattern (write the file first in CI before `podman-compose build`).

### 2 — Plain Django view, not DRF

**Decision**: Implement `/api/version/` as a plain `django.http.JsonResponse` view with no
authentication requirement.

**Rationale**: Version metadata is not sensitive; requiring auth adds friction for debugging.
DRF serialiser overhead is unnecessary for a static JSON blob.

### 3 — Alpine.js for the expand/collapse panel, no HTMX round-trip

**Decision**: Fetch `/api/version/` once via `fetch()` in the footer's Alpine component on
`x-init`. Toggle visibility client-side.

**Rationale**: The data does not change while the page is open; no HTMX requests needed after
first load.

### 4 — Footer element in `base.html`

**Decision**: Add a `<footer>` element just before `</body>`, outside the main layout div,
fixed to the bottom of the viewport. z-index above main content, below toast container.

**Rationale**: Keeps it visible on all pages without touching individual page templates.

## API / Interface Changes

- **New endpoint**: `GET /api/version/` — returns the cached `version.json` contents.
- **New URL** in `zebra_agent_web/api/urls.py`: `path("version/", views.version_info)`.
- **`AppConfig.ready()`** in `zebra_agent_web/api/apps.py`: read `version.json`, populate
  module-level `_VERSION` dict.
- **CI/CD change** in `.gitlab-ci.yml` deploy stage: generate `version.json` before build.
- **Dockerfile change**: `COPY version.json /app/version.json` in builder stage.
- **`.gitignore`**: add `version.json`.

## Data Model Changes

None. No database tables or store interfaces affected.

## Risks / Trade-offs

- [Risk] `version.json` missing in dev/test → Mitigation: graceful fallback to `"unknown"`;
  tests mock the file or rely on fallback behaviour.
- [Risk] Footer overlaps page content on short viewports → thin (1-line) collapsed state;
  panel expands upward over content.
- [Risk] CI generates `version.json` from the wrong branch → Mitigation: the deploy stage
  only runs on `master`, so `git log` always reflects the merged commit.

## Migration Plan

No DB migrations. On next deploy the CI step writes `version.json`, the image is rebuilt with
it, and the footer appears. Roll-back: revert the commit and redeploy — footer disappears.

## Open Questions

_(none)_
