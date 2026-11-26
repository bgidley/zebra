## Approach

- Squid from `docker.io/ubuntu/squid` pinned by digest; our Containerfile adds `squid.conf` and `entrypoint.sh`, which renders the allowlist (`ZEBRA_EGRESS_ALLOW` comma list plus `/etc/squid/allowlist.d/*.txt`) and an optional `cache_peer` (`ZEBRA_EGRESS_PARENT_PROXY=host:port`).
- Order of rules: deny non-CONNECT, deny CONNECT to non-443, deny private destinations (`dst`, the resolved address, so DNS rebinding is covered), allow allowlisted domains, deny all.
- httpx / openai clients already honour proxy env (`trust_env` default). Regression tests pin that. `onboarding_callback` keeps `trust_env=False` on purpose (SSRF-pinned IP fetch; onboarding is off in the work sandbox). SMTP cannot use an HTTP proxy: unsupported in the sandbox.
- `check_url` resolves DNS locally; behind the proxy that fails or leaks. When the URL's host goes through a proxy (`urllib.request.getproxies` + `proxy_bypass`), hostnames skip local resolution; IP literals and bypassed hosts (localhost) are still checked.
- CA: `docker/extra-ca.sh` concatenates the system bundle and the extra file into a bundle under `/tmp` and exports the variables. `docker/with-extra-ca.sh` wraps the daemon's non-entrypoint start.

## Risks

Squid's `dst` ACL needs working DNS in the egress container; with a parent proxy only the domain allowlist protects.
