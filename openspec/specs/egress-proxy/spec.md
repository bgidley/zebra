# egress-proxy Specification

## Purpose
TBD - created by archiving change egress-proxy-corporate-ca. Update Purpose after archive.

## Requirements

### Requirement: Egress allowlist proxy
The `zebra-egress` container SHALL tunnel HTTPS CONNECT on port 443 to allowlisted domains only, and SHALL refuse every other destination, including RFC1918, link-local and loopback addresses and CONNECT to any other port, logging each decision to stdout.

#### Scenario: Allowlisted host
- **WHEN** a client CONNECTs to an allowlisted host on 443
- **THEN** the proxy does not refuse it

#### Scenario: Private or non-443 destination
- **WHEN** a client CONNECTs to a private address, or to port 22
- **THEN** the proxy answers 403

### Requirement: Outbound clients honour the proxy
Every outbound HTTP client SHALL send its requests through `HTTPS_PROXY` / `HTTP_PROXY` unless `NO_PROXY` matches the host.

#### Scenario: Client with proxy env
- **WHEN** `HTTPS_PROXY` is set and a client calls an https host
- **THEN** the proxy receives a CONNECT for that host

### Requirement: Corporate CA
With `ZEBRA_EXTRA_CA_FILE` set the container SHALL trust that CA in addition to the system store through `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE` and `AWS_CA_BUNDLE`; with it unset nothing SHALL change.

#### Scenario: TLS-inspecting proxy
- **WHEN** a proxy presents certificates signed by the extra CA
- **THEN** the client verifies them only when the bundle is in use
