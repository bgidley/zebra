## Context

Design and threat model: `specs/onboarding-design.md` (S0, merged). Plan slice S1 of
`plan-276-278`. Another agent builds #277 pages under `/onboarding/signup/`; this change keeps its
routes and templates (`templates/onboarding/wizard.html`, `partials/step.html`, `manage.html`)
apart from those.

## Decisions

- **Workflow location**: `zebra-agent/workflows/onboarding.yaml`, not a subdirectory. Built-in
  provenance is "content hash is a shipped built-in's" (`WorkflowLibrary.builtin_hashes()`), which
  only covers top-level files, and the library only installs top-level files.
- **Provenance check**: before launch, hash the library's current YAML for the name; refuse unless
  it is in `builtin_hashes()`. A dream copy, an import or a local edit is refused (503), never run
  for a stranger.
- **Visitor steps are external waits** (`external: onboarding_visitor`), so
  `zebra.forms.is_human_task()` keeps them out of `/tasks/`, the badge and the dashboard, and the
  owner cannot be asked to fill a stranger's form. The wizard's own check is `is_visitor_task`.
- **Failure model**: each step has a `problem` route to `<step>_retry`, whose read-only reason is
  `{{__task_output_<step>.problem}}`; the retry routes back to the step. Later auto steps (S3/S4)
  route `failed` into the same retry tasks. On `problem` only the problem text is kept; on `done`
  the schema is validated, required checkboxes must be ticked, and `problem` is dropped.
- **No request user**: wizard views set the current-user contextvar to None, so a signed-in owner
  using the wizard does not own the session (`user_id` NULL) and nothing is scoped to them.
- **Only own-process reads**: `load_process(id)`, `load_definition`, `load_tasks_for_process`.
  The counts (live sessions, today's spend, idle ids) query the ORM for onboarding definitions
  only and return numbers or act inside the daemon.
- **Cookie**: `zebra_onboarding`, path `/onboarding/`, HttpOnly, SameSite=Lax, Secure when the
  request is or `SESSION_COOKIE_SECURE`; re-signed on each visit (30 days from the last visit).
  The resume link is `/onboarding/r/<token>/`, which sets the cookie and redirects away.
- **Idle** is measured by the process's `updated_at` (step progress), not page views.

## Risks

- Stores fail open: a later wizard view adding a list query would leak; a source-scan test and a
  store-trap test guard it.
- A child workflow (S3) does not inherit `__onboarding__` / `__cost_cap_usd__`; S3 must pass them.
