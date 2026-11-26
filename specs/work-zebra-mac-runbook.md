# Work Zebra on the Mac: runbook

Operator notes for the work Zebra (tracking #334). Sections are added per ticket; this file holds
the egress proxy (WZ3, #337). Design lives in `specs/work-zebra-mac-design.md` once #335 lands
it; until then see the issues and `openspec/changes/egress-proxy-corporate-ca/`.

## Egress proxy (`zebra-egress`, WZ3 #337)

The work Zebra's only way out. web, daemon and Postgres sit on an `--internal` network with no
route out; `zebra-egress` (squid) is attached to that network and the default one. Source:
`deploy/mac-container/egress/` (`Containerfile`, `squid.conf`, `entrypoint.sh`).

What it does: tunnels HTTPS (`CONNECT host:443`) to allowlisted domains and refuses everything
else: unlisted hosts, any other port, plain http, and any destination that resolves to loopback,
RFC1918, CGNAT, link-local (cloud metadata), ULA or multicast, even for an allowlisted name
(DNS rebinding). Clients see a 403 from the proxy.

### What zebra-work.sh (#336) must pass

```
zebra-egress:  -e ZEBRA_EGRESS_ALLOW=<domains>  [-e ZEBRA_EGRESS_PARENT_PROXY=host:port]
               [-v <dir>/allowlist.d:/etc/squid/allowlist.d:ro]    # networks: zebra-int + default
web, daemon:   -e HTTPS_PROXY=http://zebra-egress:3128  -e HTTP_PROXY=http://zebra-egress:3128
               -e NO_PROXY=zebra-pg,localhost
               [-e ZEBRA_EXTRA_CA_FILE=/run/zebra/corp-ca.pem -v <dir>/corp-ca.pem:/run/zebra/corp-ca.pem:ro]
```

Port 3128 is never published on the host. Build: `container build -t zebra-egress deploy/mac-container/egress`
(or `podman build`, same Containerfile).

### The allowlist

`ZEBRA_EGRESS_ALLOW` is a comma or space separated list; files `*.txt` mounted in
`/etc/squid/allowlist.d/` (one domain per line, `#` comments) are added. `host.example.com`
matches that host only; `.example.com` also matches every subdomain. Anything that is not a plain
DNS name stops the container (so a typo never silently widens or empties the policy). An empty
list is valid and refuses everything.

Typical entries:

| Host | Why |
|---|---|
| `bedrock-runtime.<region>.amazonaws.com` | Bedrock LLM (#335) |
| the sync relay host (`ZEBRA_SYNC_RELAY`, e.g. `relay.example.com`) | private skill sync (#246); needs the CONNECT transport of #338 |
| `kagi.com`, `news.kagi.com` | Kagi search / extract / news |
| OpenRouter (`openrouter.ai`) | only if OpenRouter is used there |

**Adding a host:** add it to `ZEBRA_EGRESS_ALLOW` (or a file in `allowlist.d`), then restart
`zebra-egress` only (web and daemon keep running; their connections retry). It must be a name, not
an IP address.

### Reading the log

`container logs zebra-egress` (or `podman logs`). One line per decision:

```
2026-11-26T21:57:40 10.0.0.250 TCP_TUNNEL/200 CONNECT kagi.com:443        # allowed
2026-11-26T21:57:40 10.0.0.250 TCP_DENIED/403 CONNECT example.org:443     # not on the allowlist
2026-11-26T21:57:40 10.0.0.250 TCP_DENIED/403 CONNECT 169.254.169.254:443 # private destination
```

A new `TCP_DENIED/403` for a host you expect means: allowlist it (above), or the client is
reaching somewhere unexpected, which is the thing to investigate. `TCP_TUNNEL/503` is allowed but
unreachable (DNS or network); with a parent proxy check the parent first.

### Corporate proxy in front

`ZEBRA_EGRESS_PARENT_PROXY=proxy.corp.example:8080` makes squid send every tunnel to the corporate
proxy (`never_direct`), not straight out. The allowlist and the private-range refusal still
apply here first. The private-range check uses squid's own DNS; with a parent proxy, only the
domain allowlist is authoritative for names squid cannot resolve.

### Corporate TLS inspection: the CA

A TLS-inspecting proxy re-signs certificates with the company root. Export it from the Mac
keychain (the name is whatever `security find-certificate -a -c ""` lists for your company):

```
security find-certificate -a -p -c "<Corporate Root CA name>" /Library/Keychains/System.keychain > corp-ca.pem
```

Put `corp-ca.pem` in the folder `work.env` lives in and set `ZEBRA_EXTRA_CA_FILE` to its path
inside the container. At start `docker/extra-ca.sh` (sourced by the web entrypoint; the daemon runs
through `docker/with-extra-ca.sh`) writes the system bundle plus that file to
`/tmp/zebra-ca-bundle.crt` and exports `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `AWS_CA_BUNDLE`,
`CURL_CA_BUNDLE` and the git bundle variable. A missing or non-PEM file stops the container.
Unset, nothing changes (prod). `zebra-egress` itself does not terminate or inspect TLS, so it needs
no CA, but with a parent proxy it passes the tunnel through untouched.

### Which clients use the proxy (audit, #337)

All httpx clients (OpenRouter through the OpenAI SDK, Kagi, webhook, `http_get` / `http_request`,
GitLab issue filing) honour `HTTPS_PROXY` / `NO_PROXY` by default, botocore does, and git
(subprocess) inherits the variables. A test pins this for each and a source scan fails on any new
client library or `trust_env=False`.

- `http_get` / `http_request`: behind a proxy the hostname is not resolved inside the sandbox
  (no public DNS there); the egress proxy refuses private destinations. IP literals and
  `NO_PROXY` hosts are still checked locally.
- **SMTP (`notify_email`) is not supported in the work sandbox.** SMTP cannot go through an HTTP
  proxy and a raw tunnel would defeat the allowlist. Use `notify_webhook` to an allowlisted host.
- The onboarding callback fetch deliberately ignores the proxy (SSRF-pinned) and onboarding is off
  in the sandbox.
- The nostr sync relay transport is separate (#338).

### Tests

`ZEBRA_SQUID_TEST=1 uv run pytest tests/egress` builds the image with Podman and drives it with
raw CONNECT requests (the `egress-squid` CI job). `tests/egress/test_extra_ca.py` covers the CA
bundle and an httpx call through a TLS-inspecting proxy stand-in.
