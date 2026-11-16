## Decision

Ship `tests/` in the image and allowlist it, rather than give the reviewer a separate source
snapshot.

- `tests/` is 24K today (the packages' own `tests/` already ship inside each package directory).
  A snapshot would add a second source of truth, a build step and a way for the reviewed tree to
  differ from the deployed one; the review reads "its own deployed source" by design (#190).
- The change is read-only files plus one allowlist entry. No entrypoint, env, port or runtime path
  changes, so prod behaviour is unaffected. `fixtures` directories stay denied by `DENIED_PARTS`.
- The existing `COPY` lines for `specs/`, `docs/`, `openspec/`, `scripts/`, `deploy/` set the
  precedent; free-tier constraints are unaffected (a few KB in a layer).

## Risk

The Dockerfile is the deploy path. The edit is one `COPY` of a directory that exists in the build
context and is not in `.dockerignore`. Verify after the master deploy: pipeline green, prod
`short_hash` is the merge, `/app/tests` exists in `zebra-web`.
