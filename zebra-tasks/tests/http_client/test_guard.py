"""Tests for the HTTP action guard: public-address check and credentials (F62)."""

import base64
import json
from unittest.mock import patch

import pytest

from zebra_tasks.http.guard import HttpGuardError, check_url, load_credential

MODULE = "zebra_tasks.http.guard"


def resolves_to(*addresses: str):
    async def fake(host: str, port: int) -> list[str]:
        return list(addresses)

    return patch(f"{MODULE}._resolve", fake)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("ZEBRA_HTTP_ALLOWED_PRIVATE_HOSTS", raising=False)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.3.4",
        "192.168.1.5",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "::1",
        "fd00::1",
        "fe80::1",
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
    ],
)
async def test_non_public_addresses_are_refused(address):
    with resolves_to(address), pytest.raises(HttpGuardError, match="not a public address"):
        await check_url("http://target.example/")


async def test_one_private_address_among_public_ones_is_refused():
    with resolves_to("93.184.216.34", "10.0.0.1"), pytest.raises(HttpGuardError):
        await check_url("https://mixed.example/")


async def test_public_address_is_allowed_and_host_returned():
    with resolves_to("93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"):
        assert await check_url("https://API.Example.com/v1?x=1") == "api.example.com"


async def test_ip_literal_url_is_checked():
    with pytest.raises(HttpGuardError, match="not a public address"):
        await check_url("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(HttpGuardError, match="not a public address"):
        await check_url("http://[::1]:8000/")


async def test_allow_listed_private_host_skips_the_check(monkeypatch):
    monkeypatch.setenv("ZEBRA_HTTP_ALLOWED_PRIVATE_HOSTS", " homeassistant.local , 10.0.0.9")
    with resolves_to("192.168.1.5"):
        assert await check_url("http://HomeAssistant.local:8123/api") == "homeassistant.local"
    assert await check_url("http://10.0.0.9/") == "10.0.0.9"
    with resolves_to("192.168.1.6"), pytest.raises(HttpGuardError):
        await check_url("http://other.local/")


@pytest.mark.parametrize("url", ["ftp://example.com/x", "file:///etc/passwd", "http:///nohost"])
async def test_non_http_urls_are_refused(url):
    with pytest.raises(HttpGuardError, match="http\\(s\\) URL"):
        await check_url(url)


async def test_unresolvable_host_is_refused():
    async def fail(host, port):
        raise OSError("nodename nor servname provided")

    with patch(f"{MODULE}._resolve", fail), pytest.raises(HttpGuardError, match="resolve"):
        await check_url("https://nope.invalid/")


def set_cred(monkeypatch, name: str, spec: dict) -> None:
    monkeypatch.setenv(f"ZEBRA_HTTP_CRED_{name}", json.dumps(spec))


def test_bearer_credential(monkeypatch):
    set_cred(monkeypatch, "GITHUB", {"host": "API.github.com", "type": "bearer", "token": "t0k"})
    cred = load_credential("github")
    assert cred.headers == {"Authorization": "Bearer t0k"}
    assert cred.applies_to("api.github.com")
    assert not cred.applies_to("evil.example")


def test_basic_credential(monkeypatch):
    set_cred(
        monkeypatch,
        "JIRA",
        {"host": "jira.example", "type": "basic", "username": "me", "password": "pw"},
    )
    expected = base64.b64encode(b"me:pw").decode()
    assert load_credential("jira").headers == {"Authorization": f"Basic {expected}"}


def test_header_credential(monkeypatch):
    set_cred(
        monkeypatch,
        "WEATHER",
        {"host": "api.weather.example", "type": "header", "header": "X-Api-Key", "value": "k"},
    )
    assert load_credential("weather").headers == {"X-Api-Key": "k"}


@pytest.mark.parametrize(
    "raw, message",
    [
        (None, "not configured"),
        ("not json", "not valid JSON"),
        ('{"type": "bearer", "token": "s3cret"}', "'host'"),
        ('{"host": "h", "type": "oauth", "token": "s3cret"}', "type must be"),
        ('{"host": "h", "type": "bearer"}', "missing 'token'"),
    ],
)
def test_bad_credentials_fail_without_leaking(monkeypatch, raw, message):
    if raw is None:
        monkeypatch.delenv("ZEBRA_HTTP_CRED_SVC", raising=False)
    else:
        monkeypatch.setenv("ZEBRA_HTTP_CRED_SVC", raw)
    with pytest.raises(HttpGuardError, match=message) as info:
        load_credential("svc")
    assert "s3cret" not in str(info.value)


def test_credential_name_must_be_simple():
    with pytest.raises(HttpGuardError, match="letters, digits"):
        load_credential("../etc")
