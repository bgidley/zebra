#!/bin/bash
# Optional corporate CA (#337). Source it (entrypoint.sh does) or run it through with-extra-ca.sh.
#
# With ZEBRA_EXTRA_CA_FILE unset it does nothing at all, so prod is unchanged. With it set, the
# system trust bundle plus that file (one or more PEM certificates, e.g. a TLS-inspecting
# proxy's root) are concatenated into one bundle, and every client library is pointed at it.
#
#   ZEBRA_EXTRA_CA_FILE        path to the PEM file (mount it read-only)
#   ZEBRA_SYSTEM_CA_BUNDLE     system bundle (default /etc/ssl/certs/ca-certificates.crt)
#   ZEBRA_COMBINED_CA_BUNDLE   where to write the result (default /tmp/zebra-ca-bundle.crt)
#
# A missing or non-PEM file stops the container: starting without the CA would only fail later,
# one TLS error at a time.

if [ -n "${ZEBRA_EXTRA_CA_FILE:-}" ]; then
    _system="${ZEBRA_SYSTEM_CA_BUNDLE:-/etc/ssl/certs/ca-certificates.crt}"
    _combined="${ZEBRA_COMBINED_CA_BUNDLE:-/tmp/zebra-ca-bundle.crt}"
    if [ ! -r "$ZEBRA_EXTRA_CA_FILE" ] || ! grep -q -- "-----BEGIN CERTIFICATE-----" "$ZEBRA_EXTRA_CA_FILE"; then
        echo "ZEBRA_EXTRA_CA_FILE ($ZEBRA_EXTRA_CA_FILE) is missing or holds no PEM certificate" >&2
        return 1 2>/dev/null || exit 1
    fi
    if ! { cat "$_system"; echo; cat "$ZEBRA_EXTRA_CA_FILE"; } > "$_combined"; then
        echo "cannot write $_combined" >&2
        return 1 2>/dev/null || exit 1
    fi
    export SSL_CERT_FILE="$_combined" REQUESTS_CA_BUNDLE="$_combined" AWS_CA_BUNDLE="$_combined"
    export CURL_CA_BUNDLE="$_combined" NODE_EXTRA_CA_CERTS="$ZEBRA_EXTRA_CA_FILE"
    export GIT_SSL_CAINFO="$_combined"
    echo "Extra CA from $ZEBRA_EXTRA_CA_FILE trusted via $_combined"
    unset _system _combined
fi
