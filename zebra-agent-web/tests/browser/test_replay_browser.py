"""Real-browser check of the trace's Replay form (#213, from the #170 outcome review).

Opt-in: skipped unless Playwright is installed and these are set:

- ``ZEBRA_BROWSER_BASE_URL``: a running Zebra web server (never prod's port 8000)
- ``ZEBRA_BROWSER_SESSION``: a logged-in ``sessionid`` (login is passkey-only)
- ``ZEBRA_BROWSER_PROCESS_ID``: a FAILED process to replay
- ``ZEBRA_BROWSER_ERROR``: the error it failed with, which the replay must reproduce

Run it in the Playwright container, since the host lacks Chromium's libraries::

    podman run --rm --network=host -v "$PWD":/job:Z -w /job -e ZEBRA_BROWSER_BASE_URL \
        -e ZEBRA_BROWSER_SESSION -e ZEBRA_BROWSER_PROCESS_ID -e ZEBRA_BROWSER_ERROR \
        mcr.microsoft.com/playwright/python:v1.55.0-noble \
        sh -c "pip install -q pytest playwright==1.55.0 && python -m pytest -p no:cacheprovider \
            -c /dev/null --confcutdir=zebra-agent-web/tests/browser zebra-agent-web/tests/browser"
"""

import os
import re
from urllib.parse import urlparse

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

BASE_URL = os.environ.get("ZEBRA_BROWSER_BASE_URL", "")
SESSION = os.environ.get("ZEBRA_BROWSER_SESSION", "")
PROCESS_ID = os.environ.get("ZEBRA_BROWSER_PROCESS_ID", "")
ORIGINAL_ERROR = os.environ.get("ZEBRA_BROWSER_ERROR", "")

pytestmark = pytest.mark.skipif(
    not (BASE_URL and SESSION and PROCESS_ID and ORIGINAL_ERROR),
    reason="Set ZEBRA_BROWSER_BASE_URL, _SESSION, _PROCESS_ID and _ERROR",
)


def test_replay_button_reproduces_the_failure_in_a_browser():
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        host = urlparse(BASE_URL).hostname
        context.add_cookies([{"name": "sessionid", "value": SESSION, "domain": host, "path": "/"}])
        page = context.new_page()

        page.goto(f"{BASE_URL}/processes/{PROCESS_ID}/trace/")
        page.get_by_text("Replay this process").click()
        form = page.locator(f"#replay-{PROCESS_ID} form")
        sync_api.expect(form.get_by_role("button", name="Replay")).to_be_visible()
        form.get_by_role("button", name="Replay").click()

        # The form redirects to the new replay's own trace.
        page.wait_for_url(re.compile(r"/processes/[^/]+/trace/"))
        replay_id = urlparse(page.url).path.split("/")[2]
        assert replay_id != PROCESS_ID
        sync_api.expect(page.get_by_text("Replay of").first).to_be_visible()
        assert page.locator(f'a[href*="/processes/{PROCESS_ID}/trace/"]').count() >= 1

        # It ends the way the original did: the replay's own trace shows the original's error.
        error = page.get_by_text(ORIGINAL_ERROR)
        for _ in range(30):
            if error.count():
                break
            page.wait_for_timeout(500)
            page.reload()
        sync_api.expect(error.first).to_be_visible()
        browser.close()
