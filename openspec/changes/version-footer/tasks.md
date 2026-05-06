## 1. Branch Setup

- [x] 1.1 Create feature branch: `git checkout -b fNN/version-footer` (replace NN with the GitLab issue number)

## 2. CI/CD — Generate version.json at deploy time

- [x] 2.1 Add a step to the `deploy` stage in `.gitlab-ci.yml` (before `podman-compose up -d --build`) that generates `version.json`:
  ```bash
  python scripts/gen_version.py > version.json
  ```
- [x] 2.2 Create `scripts/gen_version.py` — runs `git log master -10 --pretty=format:...` and writes a JSON object with `short_hash`, `date`, and `commits` array to stdout
- [x] 2.3 Commit a placeholder `version.json` (not gitignored); CI overwrites it in its workspace before build

## 3. Dockerfile — Copy version.json into the image

- [x] 3.1 In the **runtime** stage of `Dockerfile`, add `COPY version.json /app/version.json` (copied directly from build context; no builder stage needed since file is not used during build)
- [x] 3.2 N/A — COPY goes directly into runtime stage from build context

## 4. Django — Read version.json at startup

- [x] 4.1 Create `zebra_agent_web/api/version.py` with a `load_version()` function that reads `/app/version.json` (or `version.json` relative to `BASE_DIR` as fallback for local dev) and returns the dict; catch `FileNotFoundError` and return `{"short_hash": "unknown", "date": "", "commits": []}`
- [x] 4.2 Add a module-level `_VERSION: dict = {}` in `version.py` and call `load_version()` to populate it
- [x] 4.3 Import and call this in `AppConfig.ready()` inside `zebra_agent_web/api/apps.py` so it runs once on startup

## 5. API Endpoint

- [x] 5.1 Add `version_info` view to `zebra_agent_web/api/views.py` that returns `JsonResponse(_VERSION)` from the version module
- [x] 5.2 Wire `path("version/", views.version_info, name="version_info")` in `zebra_agent_web/api/urls.py`
- [x] 5.3 Confirm no authentication decorator on the view

## 6. Footer Template

- [x] 6.1 Add a `<footer>` element at the end of `templates/base.html` (before `</body>`) with an Alpine.js component that fetches `/api/version/` on `x-init` and stores the result in component data
- [x] 6.2 Render the short hash and date in collapsed state — single line, small muted text (e.g. `text-xs text-gray-500`)
- [x] 6.3 Implement toggle panel (expands upward via `x-show`) listing commits; each row: short hash, date, subject in monospace
- [x] 6.4 Set `z-index` so the footer sits above main content but below the toast container (`z-40` or similar)
- [x] 6.5 Set footer to `lg:pl-64` so it doesn't overlap the sidebar on large screens

## 7. Tests

- [x] 7.1 Write unit tests for `load_version()` covering: valid `version.json`, `FileNotFoundError` fallback, and malformed JSON fallback (use `tmp_path` pytest fixture to create a temp file)
- [x] 7.2 Write a Django test client test for `GET /api/version/` asserting HTTP 200, correct JSON keys, and no auth required

## 8. Lint, Format, and Commit

- [x] 8.1 Run `uv run ruff check --fix .` and `uv run ruff format .`
- [x] 8.2 Run `uv run pytest zebra-agent-web/tests/ -v` — all tests pass
- [x] 8.3 Commit: `feat: add version footer baked from git at CI build time\n\nCloses #NN`
- [x] 8.4 Push branch and verify GitLab CI pipeline passes (`lint → unit → e2e`)

## 9. Merge

- [ ] 9.1 Push branch to GitHub and open a PR referencing the GitLab issue
- [ ] 9.2 Merge to master, push to both remotes, verify deploy pipeline rebuilds image with `version.json` and footer is visible in production
