## Why

The #238 outcome review (O3) found that `test_the_page_is_behind_login` only checks that the
genealogy view is not marked login-exempt. Unit settings strip `LoginRequiredMiddleware`, so
dropping the middleware from `settings.MIDDLEWARE`, or making the view exempt some other way,
would pass CI even though prod would serve the page to anyone. Separately, #273 (O5 of #267)
still needs evidence that a prod goal has run a Commons-stamped workflow.

Refs #274, #273 (epic #41, design `specs/zebra-commons-design.md`).

## What Changes

- A unit test builds the middleware stack from the real production `MIDDLEWARE` list (so
  `LoginRequiredMiddleware` is in it), then checks that an anonymous GET of
  `/workflows/<name>/genealogy/` and of `/commons/` redirects to `LOGIN_URL` with `?next=`, and
  that a logged-in GET of each returns 200. It replaces the weaker attribute-only test.
- A read-only prod check (no goals queued, nothing written) for a goal run since the S2a deploy
  (68516eb) whose workflow file has a `commons` block with `content_sha256`, and whether it
  succeeded. The result goes on #273, and #273 is closed only if such a run exists.

## Capabilities

### New Capabilities
<!-- None -->

### Modified Capabilities
- `workflow-genealogy`: the private genealogy page is proven to be behind login.

## Outcomes

Tightened after Zebra's advisory feedback: O1 pins the exact `next` path, O4 records the
mutations and their failures, O5 states the run-to-file match and the no-evidence contingency.
Zebra suggested dropping the `/commons/` half; #274's scope asks for it, so it stays.

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | An anonymous visitor to `/workflows/<name>/genealogy/` is redirected to login | `test_pages_are_behind_login` (real prod middleware stack): 302 whose location is `LOGIN_URL` and whose decoded `next` is exactly the requested path |
| O2 | A logged-in owner still gets the genealogy page and the Commons page | The same test: a logged-in GET of each returns 200 with the page content |
| O3 | `/commons/` gets the same check in the same test | The test covers both URLs; an anonymous `/commons/` GET redirects to login |
| O4 | The test fails if the guard goes away | Two hand mutations on the branch, recorded in the commit/issue: `@login_not_required` on `workflow_genealogy` fails the genealogy case; deleting `LoginRequiredMiddleware` from `settings.py` fails both cases. The test is collected in the CI `unit` job |
| O5 | Prod state for #273 is known and recorded | A read-only prod query (`WorkflowRunModel.started_at` >= 68516eb merge, 2026-11-02T21:20:04Z; run matched by workflow name to a library file whose `commons.content_sha256` recomputes; `success=True`) is posted on #273 with run ids; #273 closed only if a non-tool goal run matched; otherwise reported and left open |
