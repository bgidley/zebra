#!/bin/bash
# zebra-egress entrypoint (#337): render the allowlist and optional parent proxy, run squid.
#
#   ZEBRA_EGRESS_ALLOW         comma / space separated domains; ".example.com" also matches subdomains
#   /etc/squid/allowlist.d/    optional mounted *.txt files, one domain per line, '#' comments
#   ZEBRA_EGRESS_PARENT_PROXY  host:port of the corporate proxy to chain to (default: connect directly)
#
# An empty allowlist is valid and refuses everything. Bad input stops the container, so a typo
# never silently widens or silently empties the policy.
set -euo pipefail

CONF_DIR="${ZEBRA_EGRESS_CONF_DIR:-/etc/squid}"
OUT="$CONF_DIR/zebra-allowed-domains.txt"
PARENT_CONF="$CONF_DIR/zebra-parent.conf"
DOMAIN_RE='^\.?[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'

: > "$OUT"
{
    echo "${ZEBRA_EGRESS_ALLOW:-}" | tr ', ' '\n\n'
    for f in "$CONF_DIR"/allowlist.d/*.txt; do
        if [ -f "$f" ]; then sed -e 's/#.*//' "$f"; fi
    done
} | tr 'A-Z' 'a-z' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | sort -u | while read -r d; do
    [ -z "$d" ] && continue
    if ! [[ "$d" =~ $DOMAIN_RE ]]; then
        echo "zebra-egress: invalid allowlist entry: '$d'" >&2
        exit 1
    fi
    echo "$d" >> "$OUT"
done
echo "zebra-egress: $(wc -l < "$OUT") allowlisted domain(s): $(tr '\n' ' ' < "$OUT")"

: > "$PARENT_CONF"
if [ -n "${ZEBRA_EGRESS_PARENT_PROXY:-}" ]; then
    if ! [[ "$ZEBRA_EGRESS_PARENT_PROXY" =~ ^[A-Za-z0-9.-]+:[0-9]+$ ]]; then
        echo "zebra-egress: ZEBRA_EGRESS_PARENT_PROXY must be host:port" >&2
        exit 1
    fi
    host="${ZEBRA_EGRESS_PARENT_PROXY%:*}"
    port="${ZEBRA_EGRESS_PARENT_PROXY##*:}"
    {
        echo "cache_peer $host parent $port 0 no-query no-digest default name=corporate"
        echo "never_direct allow all"
    } > "$PARENT_CONF"
    echo "zebra-egress: chaining to corporate proxy $host:$port"
fi

# Append the parent settings after the policy: they add routing, not access.
cat "$CONF_DIR/squid.conf" "$PARENT_CONF" > "$CONF_DIR/zebra-run.conf"
squid -k parse -f "$CONF_DIR/zebra-run.conf" 2> /tmp/squid-parse.log || {
    cat /tmp/squid-parse.log >&2
    exit 1
}

# Decisions go to the container log (podman logs zebra-egress).
touch /var/log/squid/access.log /var/log/squid/cache.log
chown proxy:proxy /var/log/squid/access.log /var/log/squid/cache.log
tail -F /var/log/squid/access.log &
tail -F /var/log/squid/cache.log >&2 &
exec squid -N -f "$CONF_DIR/zebra-run.conf"
