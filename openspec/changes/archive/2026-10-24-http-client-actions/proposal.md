## Why

Workflows can search the web (Kagi) and post to a webhook, but they cannot call an ordinary REST
API: no GET of a JSON endpoint, no authenticated write. Integrations (phase 8) and every domain in
phase 9 (calendar, finance, home) need one. F62 (#62) is that enabler.

A generic HTTP client on the prod host is also an easy way to hurt the host: it could reach
`localhost:8000`, the OCI metadata service at `169.254.169.254`, or ship a secret to an
attacker's server. Workflows are often written by an LLM, so the safety has to be in the action.

## What Changes

- **`http_get`** task action (GET/HEAD, `always_reversible`): query params, headers, optional
  credential; returns status, headers, text body and parsed JSON.
- **`http_request`** task action (POST/PUT/PATCH/DELETE, `always_irreversible`): same, plus a JSON
  or raw body. The class hint means trust gates block it below the right trust level and the golden
  gym refuses workflows that use it.
- **Internal addresses refused**: the host is resolved first and every address must be public;
  redirects are followed by hand (max 5) and each hop is checked again. Hosts listed in
  `ZEBRA_HTTP_ALLOWED_PRIVATE_HOSTS` are exempt (e.g. a LAN Home Assistant).
- **Named, host-bound credentials**: `credential: github` reads `ZEBRA_HTTP_CRED_GITHUB`
  (JSON: `host`, `type` = `bearer` | `basic` | `header`, secret fields). It is sent only to that
  host and never echoed in outputs, errors or logs. Secrets stay out of workflow YAML.
- **Bounded responses**: the body is capped (`max_bytes`, default 1 MB, max 5 MB), the timeout
  is capped at 120 s, and the output is JSON-serialisable.
- **Workflow creator rule 10** lists `http_request` as an action with outside effects that needs
  a human review step before it.
- Refactor: the nested `{{template}}` resolver moves from `notify_webhook` to
  `zebra_tasks/templating.py` so both use it.

## Non-goals

- OAuth flows and token refresh (integration provider interface, #37).
- Multipart/file upload, streaming downloads to disk, cookies/sessions.
- Full DNS-rebinding protection (pinning the connection to the vetted IP); see design risks.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A workflow can read and write a REST API | Unit tests against a mock transport: `http_get` returns a dict with exactly `status_code`, `host`, `url`, `content_type`, `headers`, `body`, `json`, `truncated`, and sends `query` params; `http_request` sends the method, headers and resolved JSON or raw body and returns the same shape; GET-only / write-only methods are enforced |
| O2 | Internal addresses are never contacted | Unit tests with stubbed DNS: loopback, RFC 1918, link-local (`169.254.169.254`), CGNAT, IPv6 loopback/ULA, IPv4-mapped IPv6, and a public name resolving to `127.0.0.1` are refused with 0 requests sent; a redirect to one is not followed (each hop re-checked); a host in `ZEBRA_HTTP_ALLOWED_PRIVATE_HOSTS` goes through. On prod, `http_get` of `http://169.254.169.254/` in `zebra-web` fails with "not a public address". Known gap: DNS rebinding between check and connect (design risks) |
| O3 | Secrets stay out of YAML, outputs, logs and other hosts | Unit tests: `credential: name` adds bearer/basic/header auth from `ZEBRA_HTTP_CRED_<NAME>`; a URL on another host is refused before sending; a cross-host redirect carries no `Authorization`; the token is absent from `output`, the failure message and captured logs |
| O4 | Every `http_request` (any method) is irreversible; `http_get` is reversible | Unit tests: a SEMI_AUTONOMOUS trust gate routes `approve` for `http_request` and `proceed` for `http_get` from the class hint with 0 LLM calls; gym `unsafe_reason` refuses `http_request`; the creator prompt's rule 10 names `http_request` |
| O5 | Responses can't blow up memory, time or properties | Unit tests: a body over `max_bytes` gives `len(body) <= max_bytes`, `truncated is True`, `json` null; timeout is capped at 120 s and `max_bytes` at 5 MB; the output round-trips through `json.dumps`; a non-2xx fails by default and is returned as output with `fail_on_status: false` |

Zebra's outcome feedback (advisory): taken: `http_request` behaviour added to O1, DNS-stub and
per-redirect checks and the allow-list key named in O2, logs and the cross-host `Authorization`
check in O3, "any method" in O4, exact bounds in O5; the external prod API call dropped from O1
(non-deterministic). Not taken: dropping the private-host allow-list (Home Assistant-style LAN
services are the main phase-9 use) and connect-time IP pinning against DNS rebinding (deferred,
see design risks).
