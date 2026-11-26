"""The zebra-egress container, run for real (#337).

Builds ``deploy/mac-container/egress`` with Podman and drives it with raw CONNECT requests.
Gated: set ``ZEBRA_SQUID_TEST=1`` (the ``egress-squid`` CI job does) and have ``podman``.
Names are made to resolve with ``--add-host``, so no test needs DNS: ``allowed.test`` is a
public address on the allowlist, ``rebind.test`` is allowlisted but resolves to RFC1918.
"""

import os
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest

EGRESS = Path(__file__).parents[2] / "deploy" / "mac-container" / "egress"

pytestmark = pytest.mark.skipif(
    os.environ.get("ZEBRA_SQUID_TEST") != "1" or shutil.which("podman") is None,
    reason="set ZEBRA_SQUID_TEST=1 with podman available to run the squid container tests",
)


def _podman(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["podman", *args], capture_output=True, text=True, check=check)


def _connect_status(port: int, target: str) -> int:
    """HTTP status squid answers to ``CONNECT target``."""
    with socket.create_connection(("127.0.0.1", port), timeout=20) as s:
        s.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
        return int(s.recv(200).split(b" ", 2)[1])


def _start(name: str, image: str, env: dict[str, str]) -> int:
    args = ["run", "-d", "--name", name, "-p", "127.0.0.1::3128"]
    args += ["--add-host", "allowed.test:1.1.1.1", "--add-host", "rebind.test:10.9.8.7"]
    for key, value in env.items():
        args += ["-e", f"{key}={value}"]
    _podman(*args, image)
    port = int(_podman("port", name, "3128/tcp").stdout.split(":")[-1])
    for _ in range(60):
        try:
            _connect_status(port, "example.invalid:443")
            return port
        except (OSError, ValueError, IndexError):
            time.sleep(0.5)
    raise AssertionError(_podman("logs", name, check=False).stdout)


@pytest.fixture(scope="module")
def image():
    tag = f"localhost/zebra-egress-test:{uuid.uuid4().hex[:8]}"
    _podman("build", "-q", "-t", tag, str(EGRESS))
    yield tag
    _podman("rmi", "-f", tag, check=False)


@pytest.fixture(scope="module")
def squid(image):
    name = f"zebra-egress-test-{uuid.uuid4().hex[:8]}"
    port = _start(name, image, {"ZEBRA_EGRESS_ALLOW": "allowed.test, rebind.test,.kagi.com"})
    yield name, port
    _podman("rm", "-f", "-t", "0", name, check=False)


def test_an_allowlisted_host_is_not_refused(squid):
    _name, port = squid

    status = _connect_status(port, "allowed.test:443")

    assert status != 403  # 200 with a route out, 502 / 503 / 504 without; never a refusal


def test_a_subdomain_of_a_dotted_entry_is_not_refused(squid):
    _name, port = squid

    assert _connect_status(port, "api.kagi.com:443") != 403


@pytest.mark.parametrize(
    "target",
    [
        "example.org:443",  # not on the allowlist
        "10.1.2.3:443",  # RFC1918
        "172.16.0.9:443",
        "192.168.1.1:443",
        "169.254.169.254:443",  # link-local / cloud metadata
        "127.0.0.1:443",  # loopback
        "localhost:443",
        "rebind.test:443",  # allowlisted name that resolves to a private address
        "allowed.test:22",  # allowlisted host, wrong port
        "allowed.test:8443",
    ],
)
def test_everything_else_is_refused(squid, target):
    _name, port = squid

    assert _connect_status(port, target) == 403


def test_plain_http_is_refused(squid):
    _name, port = squid
    with socket.create_connection(("127.0.0.1", port), timeout=20) as s:
        s.sendall(b"GET http://allowed.test/ HTTP/1.1\r\nHost: allowed.test\r\n\r\n")

        assert s.recv(200).split(b" ", 2)[1] == b"403"


def test_decisions_are_logged_to_the_container_log(squid):
    name, port = squid
    _connect_status(port, "denied-by-log-test.example:443")
    _connect_status(port, "allowed.test:443")
    time.sleep(1)

    logs = _podman("logs", name).stdout

    assert "TCP_DENIED/403 CONNECT denied-by-log-test.example:443" in logs
    assert "TCP_TUNNEL/200 CONNECT allowed.test:443" in logs or "CONNECT allowed.test:443" in logs


def test_a_bad_allowlist_entry_stops_the_container(image):
    result = _podman(
        "run", "--rm", "-e", "ZEBRA_EGRESS_ALLOW=ok.example,not_a_domain", image, check=False
    )

    assert result.returncode != 0
    assert "invalid allowlist entry: 'not_a_domain'" in result.stderr


def test_an_empty_allowlist_refuses_everything(image):
    name = f"zebra-egress-test-{uuid.uuid4().hex[:8]}"
    try:
        port = _start(name, image, {})

        assert _connect_status(port, "allowed.test:443") == 403
    finally:
        _podman("rm", "-f", "-t", "0", name, check=False)


def test_a_parent_proxy_is_chained(image):
    name = f"zebra-egress-test-{uuid.uuid4().hex[:8]}"
    try:
        _start(
            name,
            image,
            {
                "ZEBRA_EGRESS_ALLOW": "allowed.test",
                "ZEBRA_EGRESS_PARENT_PROXY": "proxy.corp.test:8080",
            },
        )

        conf = _podman("exec", name, "cat", "/etc/squid/zebra-run.conf").stdout

        assert "cache_peer proxy.corp.test parent 8080" in conf
        assert "never_direct allow all" in conf
        assert "chaining to corporate proxy proxy.corp.test:8080" in _podman("logs", name).stdout
    finally:
        _podman("rm", "-f", "-t", "0", name, check=False)


def test_a_malformed_parent_proxy_stops_the_container(image):
    result = _podman("run", "--rm", "-e", "ZEBRA_EGRESS_PARENT_PROXY=http://x", image, check=False)

    assert result.returncode != 0
    assert "must be host:port" in result.stderr
