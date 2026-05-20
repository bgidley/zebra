"""Smoke tests against the live deployed server at localhost:8000.

Run after deploy via CI. Requires:
  - SMOKE_PASSWORD env var (HTTP Basic auth password for the 'smoke' user)
  - SMOKE_BASE_URL env var (default: http://localhost:8000)

The 'smoke' user is created by the deploy step via:
  python manage.py ensure_smoke_user $SMOKE_PASSWORD
"""

import base64
import json
import os
import time
import urllib.error
import urllib.request

import pytest

BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://localhost:8000")
SMOKE_USERNAME = os.environ.get("SMOKE_USERNAME", "smoke")
SMOKE_PASSWORD = os.environ.get("SMOKE_PASSWORD", "")

pytestmark = pytest.mark.smoke


def _auth_headers() -> dict:
    credentials = base64.b64encode(f"{SMOKE_USERNAME}:{SMOKE_PASSWORD}".encode()).decode()
    return {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
    }


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{BASE_URL}{path}", headers=_auth_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _post(path: str, data: dict) -> dict:
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=body, headers=_auth_headers(), method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def test_health():
    req = urllib.request.Request(f"{BASE_URL}/api/health/", method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    assert data.get("status") in ("ok", "healthy")


def test_smoke_count_to_100():
    if not SMOKE_PASSWORD:
        pytest.skip("SMOKE_PASSWORD not set")

    resp = _post("/api/goals/", {"goal": "Count from 1 to 100", "model": "haiku"})
    assert resp["status"] == "processing", f"Unexpected status: {resp}"
    status_url = resp["status_url"]

    # Poll up to 5 minutes (60 × 5s)
    for _ in range(60):
        time.sleep(5)
        status = _get(status_url)
        if status["status"] in ("completed", "failed"):
            assert status["status"] == "completed", (
                f"Goal failed: {status.get('error')}\nOutput: {status.get('output')}"
            )
            output = str(status.get("output", ""))
            assert "100" in output, f"Expected '100' in output, got: {output!r}"
            return

    pytest.fail("Goal did not complete within 5 minutes")
