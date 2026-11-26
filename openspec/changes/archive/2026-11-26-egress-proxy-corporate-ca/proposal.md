## Why

The work Zebra (#334) may only reach the outside world through an egress allowlist proxy, behind a TLS-inspecting corporate proxy (#337, WZ3).

## What Changes

- `deploy/mac-container/egress/`: `zebra-egress` squid container (pinned digest). Domain allowlist from env / mounted file, deny RFC1918 / link-local / loopback and CONNECT to non-443, optional parent (corporate) proxy, allow/deny log on stdout.
- Audit of every outbound client for `HTTPS_PROXY` / `NO_PROXY`, with recording-proxy tests per client. `http_get` / `http_request` skip their local DNS check for hosts that go through a proxy (the egress proxy enforces the private-range denial; the sandbox network has no public DNS).
- `ZEBRA_EXTRA_CA_FILE`: combined CA bundle built at container start (`docker/extra-ca.sh`), with `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `AWS_CA_BUNDLE`, `CURL_CA_BUNDLE` and the version-control client bundle variable pointed at it. No-op when unset.
- Runbook `specs/work-zebra-mac-runbook.md` (egress section); SMTP decision recorded.

## Non-goals

`zebra-work.sh` (#336), the nostr relay transport through the proxy (#338), a tunnel for SMTP.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Allowlisted hosts work through the egress proxy; anything else (RFC1918 / link-local / loopback, a name resolving to one, non-443 CONNECT) is refused | gated test against a real squid container, run in CI (podman) |
| O2 | Every outbound client in Zebra honours `HTTPS_PROXY` (SMTP documented as unsupported) | unit tests per client with a recording proxy |
| O3 | TLS works behind a TLS-inspecting proxy given the corporate CA, and prod is unchanged when `ZEBRA_EXTRA_CA_FILE` is unset | mitm-CA test of `extra-ca.sh` + httpx through a proxy (fails without the CA, passes with it); unset leaves env and trust untouched |
