"""Publishing an OFFER to a real public strfry relay (#231).

Starts a throwaway strfry container (the pinned image of the Quadlet) with the repo's public
relay config and write policy on a random loopback port, never a prod relay or port 8000. The
receipt signer runs in-process over the policy's journal. Skips with a reason when podman or
the image is missing, and in CI unless ``ZEBRA_COMMONS_RELAY_IT=1`` (CI shares the prod host).

Run it: ``uv run pytest zebra-agent/tests/test_commons_public_relay_integration.py -v``
(``podman pull docker.io/dockurr/strfry:latest`` once).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from zebra_agent.commons import keys, kinds
from zebra_agent.commons.client import Filter, PublishRefused
from zebra_agent.commons.events import COMMONS_TAG, sign_event
from zebra_agent.commons.identity import make_device_cert
from zebra_agent.commons.mirror import InMemoryCommonsMirror
from zebra_agent.commons.offer import offer_content, offer_stats, verify_offer
from zebra_agent.commons.publisher import CommonsPublisher
from zebra_agent.commons.receipts import ReceiptSigner, receipt_order
from zebra_agent.commons.relay import RelayCommonsClient
from zebra_agent.metrics import WorkflowStats

REPO = Path(__file__).resolve().parents[2]
RELAY_DIR = REPO / "deploy" / "podman" / "commons-relay"
IMAGE = "docker.io/dockurr/strfry:latest"
YAML = """name: Capital Facts
version: 1
first_task: answer
tasks:
  answer:
    name: Answer
    action: llm_call
    properties:
      prompt: "Answer: {{goal}}"
"""


def _skip_reason() -> str | None:
    if os.environ.get("CI") and os.environ.get("ZEBRA_COMMONS_RELAY_IT") != "1":
        return "relay integration test is off in CI (set ZEBRA_COMMONS_RELAY_IT=1 to run it)"
    if shutil.which("podman") is None:
        return "podman is not installed"
    found = subprocess.run(["podman", "image", "exists", IMAGE], capture_output=True)
    if found.returncode != 0:
        return f"{IMAGE} is not pulled (podman pull {IMAGE})"
    return None


pytestmark = pytest.mark.skipif(_skip_reason() is not None, reason=_skip_reason() or "")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert port != 8000
    return port


def _wait_port(port: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"port {port} did not come up")


@pytest.fixture
def relay(tmp_path):
    operator = keys.generate_secret_key()
    port = _free_port()
    name = f"zebra-commons-it-{uuid.uuid4().hex[:8]}"
    conf, receipts, db = tmp_path / "conf", tmp_path / "receipts", tmp_path / "db"
    for d in (conf, receipts, db):
        d.mkdir()
    shutil.copy(RELAY_DIR / "strfry.conf", conf / "strfry.conf")
    shutil.copy(RELAY_DIR / "write_policy.py", conf / "write_policy.py")
    (conf / "write_policy.py").chmod(0o755)
    (conf / "policy.json").write_text(json.dumps({"operator_pubkey": keys.public_key(operator)}))
    subprocess.run(
        [
            "podman", "run", "-d", "--name", name,
            "-p", f"127.0.0.1:{port}:7777",
            "-v", f"{conf}:/etc/zebra-commons:ro,Z",
            "-v", f"{receipts}:/receipts:Z",
            "-v", f"{db}:/app/strfry-db:Z",
            "-e", "ZEBRA_COMMONS_POLICY=/etc/zebra-commons/policy.json",
            "-e", "ZEBRA_COMMONS_JOURNAL=/receipts/journal.jsonl",
            "--entrypoint", "/app/strfry",
            IMAGE, "--config=/etc/zebra-commons/strfry.conf", "relay",
        ],
        check=True, capture_output=True, timeout=60,
    )  # fmt: skip
    try:
        _wait_port(port)
        yield {
            "url": f"ws://127.0.0.1:{port}/commons",
            "operator": operator,
            "journal": receipts / "journal.jsonl",
            "state": tmp_path / "signer.json",
        }
    finally:
        subprocess.run(["podman", "rm", "-f", name], capture_output=True, timeout=60)


async def test_offer_on_a_real_public_relay_has_a_receipt_and_verifies(relay):
    from zebra_agent.commons.nostr import NostrSdkTransport

    zebra_secret, device = keys.generate_secret_key(), keys.generate_secret_key()
    cert = make_device_cert(
        zebra_secret, keys.public_key(device), label="Home", sphere="home", observed=False
    )
    publisher_client = RelayCommonsClient(NostrSdkTransport(relay["url"], timeout=5), private=False)
    reader = RelayCommonsClient(NostrSdkTransport(relay["url"], timeout=5), private=False)
    signer_client = RelayCommonsClient(NostrSdkTransport(relay["url"], timeout=5), private=False)
    signer = ReceiptSigner(relay["journal"], relay["state"], signer_client, relay["operator"])
    signing = asyncio.create_task(signer.run(interval=0.2))
    publisher = CommonsPublisher(
        canonical=publisher_client,
        device_secret=device,
        zebra_pubkey=keys.public_key(zebra_secret),
        mirror=InMemoryCommonsMirror(),
        certs=[cert],
        receipt_pubkey=keys.public_key(relay["operator"]),
        receipt_wait=15,
    )
    try:
        content = offer_content(
            name="Capital Facts",
            summary="Answers capital-city questions.",
            use_when="A capital-city question",
            stats=offer_stats(WorkflowStats("Capital Facts", 5, 5), None),
            actions=["llm_call"],
            golden_tasks=[{"goal": "Capital of Australia?", "criteria": ["Canberra"]}],
            yaml=YAML,
        )
        result = await publisher.publish_offer(content, {})
        assert result["receipt_seq"] is not None

        # A reader with no account (no NIP-42) sees the offer, its cert and the receipt.
        [offer] = await reader.fetch([Filter(kinds=(kinds.OFFER_KIND,))])
        certs = await reader.fetch([Filter(kinds=(kinds.DEVICE_CERT_KIND,))])
        npub = keys.npub_encode(keys.public_key(zebra_secret))
        check = verify_offer(offer, certs, expected_zebra=keys.npub_decode(npub))
        assert check.ok, check.reason
        receipts = await reader.fetch([Filter(kinds=(kinds.RECEIPT_KIND,), events=(offer.id,))])
        assert (
            receipt_order(receipts, keys.public_key(relay["operator"]))[offer.id]
            == result["receipt_seq"]
        )

        # The relay's own policy refuses what the client hard filter would also refuse.
        rogue = sign_event(device, 1, [COMMONS_TAG], "hello")
        raw = RelayCommonsClient(NostrSdkTransport(relay["url"], timeout=5), private=True)
        with pytest.raises(PublishRefused):
            await raw.publish(rogue)
        await raw.close()
    finally:
        signing.cancel()
        for client in (publisher_client, reader, signer_client):
            await client.close()
