### Requirement: Read a REST API with http_get
The `http_get` task action SHALL send a GET (or HEAD) request with optional `query` params,
`headers` and `credential`, resolving `{{templates}}` in the URL and in string values, and SHALL
return `status_code`, `host`, `url` (without query string), `content_type`, `headers`, `body`,
`json` and `truncated`. Its `reversibility_hint` SHALL be `always_reversible`.

#### Scenario: JSON endpoint
- **WHEN** `http_get` calls an endpoint that replies 200 with `application/json`
- **THEN** the output has `status_code` 200, the text in `body` and the parsed value in `json`

#### Scenario: Query params
- **WHEN** `query` is `{"q": "{{topic}}"}` and `topic` is `zebras`
- **THEN** the request URL carries `q=zebras`

### Requirement: Write to a REST API with http_request
The `http_request` task action SHALL send POST, PUT, PATCH or DELETE with an optional `json`
or `body`, and SHALL refuse any other method. Its `reversibility_hint` SHALL be
`always_irreversible`, and the workflow creator prompt SHALL list it among actions that need a
human review step before them.

#### Scenario: JSON write
- **WHEN** `http_request` posts `json: {"title": "{{goal}}"}`
- **THEN** the body sent is the resolved JSON and the response is returned as output

#### Scenario: Gate treats it as irreversible
- **WHEN** a trust gate assesses a task using `http_request`
- **THEN** it is irreversible from the class hint, without an LLM call

### Requirement: Internal addresses are refused
Both actions SHALL resolve the host and refuse the request, without sending it, when any address
is not globally routable (loopback, private, link-local, CGNAT, unique-local, reserved,
multicast, including IPv4-mapped IPv6), unless the host is listed in
`ZEBRA_HTTP_ALLOWED_PRIVATE_HOSTS`. Redirects SHALL be followed by the action (at most 5) and
each hop SHALL be checked the same way.

#### Scenario: Cloud metadata
- **WHEN** a task requests `http://169.254.169.254/`
- **THEN** it fails saying the host is not a public address and no request is sent

#### Scenario: Redirect to localhost
- **WHEN** a public URL redirects to `http://127.0.0.1:8000/`
- **THEN** the task fails and the redirect target is not requested

#### Scenario: Allow-listed LAN host
- **WHEN** `homeassistant.local` is in `ZEBRA_HTTP_ALLOWED_PRIVATE_HOSTS` and resolves to `192.168.1.5`
- **THEN** the request is sent

### Requirement: Named host-bound credentials
A `credential: <name>` property SHALL load JSON from `ZEBRA_HTTP_CRED_<NAME>` with a `host` and
a `type` of `bearer`, `basic` or `header`, and apply that auth only to requests to that host.
The secret SHALL NOT appear in the task output, failure messages or logs.

#### Scenario: Bearer token
- **WHEN** `credential: github` and `ZEBRA_HTTP_CRED_GITHUB` is `{"host": "api.github.com", "type": "bearer", "token": "t0k"}`
- **THEN** a request to `api.github.com` carries `Authorization: Bearer t0k`

#### Scenario: Wrong host
- **WHEN** the same credential is used with a URL on `evil.example`
- **THEN** the task fails before sending and the message names the credential, not the token

#### Scenario: Cross-host redirect
- **WHEN** `api.github.com` redirects to another host
- **THEN** the next request carries no credential auth

### Requirement: Bounded responses
The response body SHALL be read up to `max_bytes` (default 1 MB, at most 5 MB) and flagged
`truncated` when cut; the timeout SHALL be at most 120 s; non-2xx responses SHALL fail the task
unless `fail_on_status` is false; the output SHALL be JSON-serialisable.

#### Scenario: Oversized body
- **WHEN** the reply is larger than `max_bytes`
- **THEN** `body` holds the first `max_bytes` bytes, `truncated` is true and `json` is null

#### Scenario: Error status kept
- **WHEN** the reply is 404 and `fail_on_status` is false
- **THEN** the task succeeds with `status_code` 404
