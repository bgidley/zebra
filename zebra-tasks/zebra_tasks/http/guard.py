"""Safety checks for the HTTP task actions (F62).

``check_url`` refuses URLs whose host resolves to a non-public address, so a
workflow cannot reach prod on localhost, the cloud metadata service or the LAN.
``load_credential`` reads a named, host-bound credential from the environment,
so secrets stay out of workflow YAML and are only ever sent to their own host.
"""

import asyncio
import base64
import ipaddress
import json
import os
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

ALLOWED_PRIVATE_HOSTS_ENV = "ZEBRA_HTTP_ALLOWED_PRIVATE_HOSTS"
CREDENTIAL_ENV_PREFIX = "ZEBRA_HTTP_CRED_"

_ALLOWED_SCHEMES = ("http", "https")
_CREDENTIAL_NAME = re.compile(r"^[A-Z0-9_]+$")
_CREDENTIAL_TYPES = ("bearer", "basic", "header")


class HttpGuardError(Exception):
    """A request was refused before it was sent. The message is safe to show."""


@dataclass(frozen=True)
class Credential:
    """A named credential bound to one host."""

    name: str
    host: str
    headers: dict[str, str]

    def applies_to(self, host: str) -> bool:
        """Whether this credential may be sent to ``host``."""
        return host.lower() == self.host


def _allowed_private_hosts() -> set[str]:
    raw = os.environ.get(ALLOWED_PRIVATE_HOSTS_ENV, "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


async def _resolve(host: str, port: int) -> list[str]:
    """Return every address ``host`` resolves to."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


async def check_url(url: str) -> str:
    """Check that ``url`` is http(s) and its host resolves only to public addresses.

    Args:
        url: The fully resolved URL.

    Returns:
        The URL's host, lower-cased.

    Raises:
        HttpGuardError: If the URL is malformed, cannot be resolved, or any address
            it resolves to is not public and the host is not allow-listed.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        raise HttpGuardError("URL must be an http(s) URL with a host")
    host = parsed.hostname.lower()
    if host in _allowed_private_hosts():
        return host
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as e:
        raise HttpGuardError(f"Invalid port in URL for {host}") from e
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            addresses = await _resolve(host, port)
        except (OSError, UnicodeError) as e:
            raise HttpGuardError(f"Could not resolve host {host}") from e
    if not addresses or not all(_is_public(a) for a in addresses):
        raise HttpGuardError(
            f"Host {host} is not a public address; add it to {ALLOWED_PRIVATE_HOSTS_ENV} "
            "to allow it"
        )
    return host


def load_credential(name: str) -> Credential:
    """Load the credential ``name`` from ``ZEBRA_HTTP_CRED_<NAME>``.

    The variable holds JSON with ``host`` and ``type``: ``bearer`` (``token``),
    ``basic`` (``username``, ``password``) or ``header`` (``header``, ``value``).
    Error messages name the credential, never its secret.

    Raises:
        HttpGuardError: If the name is invalid, the variable is missing or malformed.
    """
    key = name.strip().upper()
    if not _CREDENTIAL_NAME.match(key):
        raise HttpGuardError("Credential name must contain only letters, digits and _")
    env_name = CREDENTIAL_ENV_PREFIX + key
    raw = os.environ.get(env_name)
    if not raw:
        raise HttpGuardError(f"Credential '{name}' is not configured ({env_name} is not set)")
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HttpGuardError(f"Credential '{name}' is not valid JSON") from e
    if not isinstance(spec, dict) or not spec.get("host"):
        raise HttpGuardError(f"Credential '{name}' must be a JSON object with a 'host'")

    kind = spec.get("type")
    try:
        if kind == "bearer":
            headers = {"Authorization": f"Bearer {spec['token']}"}
        elif kind == "basic":
            pair = f"{spec['username']}:{spec['password']}".encode()
            headers = {"Authorization": f"Basic {base64.b64encode(pair).decode()}"}
        elif kind == "header":
            headers = {str(spec["header"]): str(spec["value"])}
        else:
            raise HttpGuardError(
                f"Credential '{name}' type must be one of {', '.join(_CREDENTIAL_TYPES)}"
            )
    except KeyError as e:
        raise HttpGuardError(f"Credential '{name}' ({kind}) is missing '{e.args[0]}'") from e
    return Credential(name=name, host=str(spec["host"]).strip().lower(), headers=headers)
