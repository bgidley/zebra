"""ZEBRA_EXTRA_CA_FILE: a corporate CA joins the trust store; unset changes nothing (#337).

The mitm test stands in for a TLS-inspecting corporate proxy: a CONNECT proxy tunnels to a TLS
server whose certificate comes from a private CA, so the client only verifies it when the
combined bundle built by ``docker/extra-ca.sh`` is in use.
"""

import asyncio
import datetime
import ssl
import subprocess
import sys
from pathlib import Path

import certifi
import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "docker" / "extra-ca.sh"
sys.path.insert(0, str(ROOT / "tests" / "support"))

from recording_proxy import RecordingProxy  # noqa: E402

VARS = ["SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "AWS_CA_BUNDLE", "CURL_CA_BUNDLE"]


def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _make_ca_and_leaf(host: str):
    now = datetime.datetime.now(datetime.UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca = (
        x509.CertificateBuilder()
        .subject_name(_name("Test Corp Root"))
        .issuer_name(_name("Test Corp Root"))
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf = (
        x509.CertificateBuilder()
        .subject_name(_name(host))
        .issuer_name(ca.subject)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False
        )
        .sign(ca_key, hashes.SHA256())
    )
    return ca, leaf, leaf_key


def _pem(cert) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def _run_script(tmp_path, extra_env: dict[str, str]) -> subprocess.CompletedProcess:
    env = {
        "PATH": "/usr/bin:/bin",
        "ZEBRA_SYSTEM_CA_BUNDLE": certifi.where(),
        "ZEBRA_COMBINED_CA_BUNDLE": str(tmp_path / "bundle.crt"),
        **extra_env,
    }
    return subprocess.run(
        ["bash", "-c", f". {SCRIPT} && env"], env=env, capture_output=True, text=True
    )


def _env_of(result: subprocess.CompletedProcess) -> dict[str, str]:
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def test_unset_changes_nothing(tmp_path):
    result = _run_script(tmp_path, {})

    assert result.returncode == 0
    assert not (tmp_path / "bundle.crt").exists()
    env = _env_of(result)
    assert not [v for v in VARS if v in env]


def test_set_builds_the_combined_bundle_and_points_the_clients_at_it(tmp_path):
    ca, _leaf, _key = _make_ca_and_leaf("example.test")
    extra = tmp_path / "corp.pem"
    extra.write_bytes(_pem(ca))

    result = _run_script(tmp_path, {"ZEBRA_EXTRA_CA_FILE": str(extra)})

    assert result.returncode == 0, result.stderr
    bundle = tmp_path / "bundle.crt"
    text = bundle.read_text()
    assert Path(certifi.where()).read_text().strip() in text
    assert _pem(ca).decode().strip() in text
    env = _env_of(result)
    assert {v: env[v] for v in VARS} == dict.fromkeys(VARS, str(bundle))


@pytest.mark.parametrize("content", [None, "not a certificate\n"])
def test_a_missing_or_non_pem_file_stops_start_up(tmp_path, content):
    extra = tmp_path / "corp.pem"
    if content is not None:
        extra.write_text(content)

    result = _run_script(tmp_path, {"ZEBRA_EXTRA_CA_FILE": str(extra)})

    assert result.returncode != 0
    assert "ZEBRA_EXTRA_CA_FILE" in result.stderr


async def _tls_server(tmp_path, leaf, leaf_key):
    cert_file, key_file = tmp_path / "leaf.pem", tmp_path / "leaf.key"
    cert_file.write_bytes(_pem(leaf))
    key_file.write_bytes(
        leaf_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)

    async def handle(reader, writer):
        try:
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
            await writer.drain()
        finally:
            writer.close()

    return await asyncio.start_server(handle, "127.0.0.1", 0, ssl=context)


async def test_tls_inspecting_proxy_verifies_only_with_the_extra_ca(tmp_path, monkeypatch):
    ca, leaf, leaf_key = _make_ca_and_leaf("example.test")
    server = await _tls_server(tmp_path, leaf, leaf_key)
    proxy = RecordingProxy(tunnel_to=("127.0.0.1", server.sockets[0].getsockname()[1]))
    await proxy.start()
    monkeypatch.setenv("HTTPS_PROXY", proxy.url)
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    try:
        async with httpx.AsyncClient() as client:
            with pytest.raises(httpx.ConnectError, match="CERTIFICATE_VERIFY_FAILED"):
                await client.get("https://example.test/")

        extra = tmp_path / "corp.pem"
        extra.write_bytes(_pem(ca))
        env = _env_of(_run_script(tmp_path, {"ZEBRA_EXTRA_CA_FILE": str(extra)}))
        monkeypatch.setenv("SSL_CERT_FILE", env["SSL_CERT_FILE"])
        async with httpx.AsyncClient() as client:
            response = await client.get("https://example.test/")

        assert (response.status_code, response.text) == (200, "ok")
        assert proxy.connects.count("example.test:443") == 2
    finally:
        await proxy.stop()
        server.close()
        await server.wait_closed()
