## Context

`zebra_agent_web/test_settings.py` removes `LoginRequiredMiddleware` from `MIDDLEWARE` so most
unit tests can use an anonymous client. Because `test_settings` star-imports `settings` and calls
`MIDDLEWARE.remove(...)`, the list object in `zebra_agent_web.settings` is mutated too, so the
test cannot simply re-read it.

## Decisions

- **Rebuild the prod stack from source.** The test reads the real `MIDDLEWARE` from
  `settings.py` by evaluating that one assignment with `ast`, then drops only
  `SetupRedirectMiddleware` (it is only about first-run setup and causes SQLite lock contention).
  A test that hard-coded its own list would keep passing if someone dropped the middleware from
  `settings.py`. Reading the source catches that.
- **One parametrised test over both pages** (`/workflows/<name>/genealogy/`, `/commons/`), using
  Django's sync `Client` with `force_login` for the logged-in case. Commons is switched on
  (`COMMONS_ENABLED`, key dir in `tmp_path`) so the logged-in `/commons/` GET is 200, not 404.
- **Prod check is read-only**: `podman exec zebra-web python manage.py shell -c` with
  `WorkflowRunModel` reads and library file reads only.

## Risks

- Parsing `settings.py` with `ast` depends on `MIDDLEWARE = [...]` staying a literal list. If it
  stops being one the test fails loudly, which is what we want.
