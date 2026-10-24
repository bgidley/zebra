## Context

Task actions run inside `zebra-web` / the daemon on the single prod host, next to prod on
`localhost:8000` and the OCI metadata service. `notify_webhook` already uses `httpx`; `kagi_*`
read their key from an env var. Trust gates take reversibility from the action class's
`reversibility_hint` when it is not `context_dependent`. Gating is opt-in: a workflow adds a
`trust_gate` task, and the workflow creator's rule 10 asks for a human review before effects.

## Decisions

- **Two actions, not one.** The hint is per class. `http_get` (GET/HEAD) is `always_reversible`
  and `http_request` (POST/PUT/PATCH/DELETE) is `always_irreversible`, so the gate and the gym
  decide without an LLM call. One `context_dependent` action would pay for an LLM call on every
  gated GET and could misjudge a DELETE.
- **Resolve, then check every address.** `guard.check_url()` parses the URL (http/https, host
  required), resolves it with `getaddrinfo`, unwraps IPv4-mapped IPv6, and refuses any address
  that is not `is_global` (or is multicast). That covers loopback, RFC 1918, link-local, CGNAT,
  ULA and reserved ranges. `ZEBRA_HTTP_ALLOWED_PRIVATE_HOSTS` (comma-separated hostnames/IPs)
  skips the check for named hosts only.
- **Manual redirects.** `follow_redirects=False`; up to 5 hops, each checked with `check_url()`.
  A 303, or a 301/302 on a write, becomes a GET without a body (browser behaviour).
- **Credentials by name, bound to a host.** `ZEBRA_HTTP_CRED_<NAME>` holds JSON:
  `{"host": "api.github.com", "type": "bearer", "token": "..."}`; `basic` takes `username`
  and `password`; `header` takes `header` and `value` (API keys). The name is upper-cased and must
  match `[A-Z0-9_]+`. The request fails if the URL host differs from `host`, and the auth is left
  off any redirect hop to another host. Only the credential *name* appears in errors.
- **Bounded body.** Read with `client.stream()` up to `max_bytes` (default 1 MB, hard max 5 MB);
  decode as text with the response charset (`errors="replace"`); parse JSON when the content type
  says JSON and the body is complete. `set-cookie` is dropped from the returned headers; the
  returned `url` has no query string (it may carry keys).
- **Status handling.** Non-2xx fails by default with the status and the first 200 chars of the
  body. `fail_on_status: false` returns it as normal output so a later task can branch.

## Output

`status_code`, `host`, `url` (no query), `content_type`, `headers`, `body`, `json` (or null),
`truncated`.

## Risks

- **DNS rebinding**: `httpx` resolves the host again after the check, so a hostile DNS server
  could answer differently the second time. Closing this needs a transport pinned to the vetted IP
  (TLS SNI makes that fiddly); deferred. Exposure is limited: what gets through can only be read
  back by a workflow, and writes are irreversible-gated.
- `http_get` is reversible, so an ungated workflow can GET any public URL, and a GET can leak data
  in the query string. That is the same exposure as `kagi_extract` today.
