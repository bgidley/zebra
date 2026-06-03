"""Fixtures for smoke tests against a live podman container.

Set ZEBRA_SMOKE_URL to point at the running container (default: http://localhost:8001).
Set ZEBRA_SMOKE_SESSION to a valid Django session key — the CI job creates one via
manage.py shell after starting the container.
"""

import os

import httpx
import pytest

BASE_URL = os.environ.get("ZEBRA_SMOKE_URL", "http://localhost:8001")
SESSION_KEY = os.environ.get("ZEBRA_SMOKE_SESSION", "")


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture
async def client(base_url: str):
    async with httpx.AsyncClient(base_url=base_url, follow_redirects=True) as c:
        yield c


@pytest.fixture
async def logged_in_client(client: httpx.AsyncClient):
    """Return a client authenticated as the smoke user via injected session cookie."""
    if not SESSION_KEY:
        pytest.skip("ZEBRA_SMOKE_SESSION not set — cannot authenticate without WebAuthn")
    client.cookies.set("sessionid", SESSION_KEY)
    yield client
