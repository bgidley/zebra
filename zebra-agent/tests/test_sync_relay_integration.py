"""Skill sync over a real strfry relay (#246): the S3b-1 home + observed work scenario.

Starts a throwaway strfry container (the pinned image of the Quadlet) with the repo's config
and write policy on a random loopback port, never the prod relay or port 8000. The receipt
signer runs in-process over the policy's journal. Skips with a reason when podman or the image
is missing, and in CI unless ``ZEBRA_SYNC_RELAY_IT=1`` (CI shares the prod host).

Run it: ``uv run pytest zebra-agent/tests/test_sync_relay_integration.py -v``
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
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState
from zebra.storage.memory import InMemoryStore

from tests.test_skill_sync_e2e import (
    CHECKLIST,
    OWNER,
    WORKFLOWS,
    Device,
    Stats,
    _registry,
    llm,  # noqa: F401 - fixture
)
from zebra_agent.commons import keys
from zebra_agent.commons.client import SKILL_KIND, Filter, PublishRefused
from zebra_agent.commons.events import COMMONS_TAG, sign_event
from zebra_agent.commons.identity import make_device_cert, make_device_revoke
from zebra_agent.commons.receipts import RECEIPT_KIND, ReceiptSigner, receipt_order
from zebra_agent.commons.relay import Outbox, RelayCommonsClient
from zebra_agent.commons.sync import SyncService, share_records
from zebra_agent.library import WorkflowLibrary
from zebra_agent.storage.trust import InMemoryTrustStore

REPO = Path(__file__).resolve().parents[2]
RELAY_DIR = REPO / "deploy" / "podman" / "sync-relay"
IMAGE = "docker.io/dockurr/strfry:latest"


def _skip_reason() -> str | None:
    if os.environ.get("CI") and os.environ.get("ZEBRA_SYNC_RELAY_IT") != "1":
        return "relay integration test is off in CI (set ZEBRA_SYNC_RELAY_IT=1 to run it)"
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


def _wait_port(port: int, up: bool, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                if up:
                    return
        except OSError:
            if not up:
                return
        time.sleep(0.2)
    raise TimeoutError(f"port {port} did not come {'up' if up else 'down'}")


class Relay:
    """A throwaway strfry with the repo's config and write policy."""

    def __init__(self, root: Path, zebra_pubkeys: list[str], operator_pubkey: str):
        self.port = _free_port()
        self.url = f"ws://127.0.0.1:{self.port}/sync"
        self.name = f"zebra-sync-it-{uuid.uuid4().hex[:8]}"
        self.conf, self.receipts, self.db = root / "conf", root / "receipts", root / "db"
        for d in (self.conf, self.receipts, self.db):
            d.mkdir(parents=True)
        conf = (RELAY_DIR / "strfry.conf").read_text()
        conf = conf.replace('serviceUrl = "wss://ZEBRA_HOST/sync"', f'serviceUrl = "{self.url}"')
        assert self.url in conf
        (self.conf / "strfry.conf").write_text(conf)
        shutil.copy(RELAY_DIR / "write_policy.py", self.conf / "write_policy.py")
        (self.conf / "write_policy.py").chmod(0o755)
        (self.conf / "allowlist.json").write_text(
            json.dumps({"zebra_pubkeys": zebra_pubkeys, "operator_pubkey": operator_pubkey})
        )
        self.journal = self.receipts / "journal.jsonl"

    def start(self) -> None:
        subprocess.run(
            [
                "podman", "run", "-d", "--name", self.name,
                "-p", f"127.0.0.1:{self.port}:7777",
                "-v", f"{self.conf}:/etc/zebra-sync:ro,Z",
                "-v", f"{self.receipts}:/receipts:Z",
                "-v", f"{self.db}:/app/strfry-db:Z",
                "-e", "ZEBRA_SYNC_ALLOWLIST=/etc/zebra-sync/allowlist.json",
                "-e", "ZEBRA_SYNC_JOURNAL=/receipts/journal.jsonl",
                "--entrypoint", "/app/strfry",
                IMAGE, "--config=/etc/zebra-sync/strfry.conf", "relay",
            ],
            check=True, capture_output=True, timeout=60,
        )  # fmt: skip
        _wait_port(self.port, up=True)

    def stop(self) -> None:
        subprocess.run(["podman", "stop", "-t", "2", self.name], capture_output=True, timeout=60)
        _wait_port(self.port, up=False)

    def resume(self) -> None:
        deadline = time.time() + 30
        while True:  # rootless port forwarding can take a moment to release the port
            done = subprocess.run(["podman", "start", self.name], capture_output=True, timeout=60)
            if done.returncode == 0 or time.time() > deadline:
                break
            time.sleep(1)
        _wait_port(self.port, up=True)

    def remove(self) -> None:
        subprocess.run(["podman", "rm", "-f", self.name], capture_output=True, timeout=60)

    def exec(self, *args: str) -> subprocess.CompletedProcess:
        conf = "--config=/etc/zebra-sync/strfry.conf"
        return subprocess.run(
            ["podman", "exec", self.name, "/app/strfry", conf, *args],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def journal_entries(self) -> list[dict]:
        if not self.journal.exists():
            return []
        return [json.loads(line) for line in self.journal.read_text().splitlines()]


@pytest.fixture
async def world(tmp_path, llm):  # noqa: F811 - the e2e fixture
    """One Zebra, home (unobserved) and work (observed) deployments, a real private relay."""
    from zebra_agent.commons.nostr import NostrSdkTransport

    zebra_secret = keys.generate_secret_key()
    zebra_pubkey = keys.public_key(zebra_secret)
    operator = keys.generate_secret_key()
    relay = Relay(tmp_path / "relay", [zebra_pubkey], keys.public_key(operator))
    relay.start()
    builtins = tmp_path / "builtins"
    builtins.mkdir()
    for f in ("skill_share.yaml", "skill_receive.yaml"):
        shutil.copy(WORKFLOWS / f, builtins / f)
    spheres = {"home": False, "work": True}
    secrets = {s: keys.generate_secret_key() for s in spheres}
    certs = {
        s: make_device_cert(
            zebra_secret, keys.public_key(secrets[s]), label=f"{s} device", sphere=s, observed=o
        )
        for s, o in spheres.items()
    }
    clients: list[RelayCommonsClient] = []

    def device(sphere: str) -> Device:
        stats = Stats()
        library = WorkflowLibrary(
            tmp_path / sphere, stats, owner_user_id=OWNER, sphere=sphere, device=sphere
        )
        library.copy_builtin_workflows(builtins)
        client = RelayCommonsClient(
            NostrSdkTransport(relay.url, secrets[sphere], timeout=5),
            outbox=Outbox(tmp_path / sphere / ".sync" / "outbox.jsonl"),
        )
        clients.append(client)
        sync = SyncService(
            client=client,
            device_secret=secrets[sphere],
            zebra_pubkey=zebra_pubkey,
            sphere=sphere,
            observed=spheres[sphere],
            certs=[certs[sphere]],  # only its own cert: the sibling is learnt from the relay
            device_label=f"{sphere} device",
            receipt_pubkey=keys.public_key(operator),
        )
        trust = InMemoryTrustStore()
        engine = WorkflowEngine(
            InMemoryStore(),
            _registry(),
            extras={
                "__workflow_library__": library,
                "__commons_sync__": sync,
                "__trust_store__": trust,
            },
        )
        return Device(sphere, library, engine, sync, stats, trust)

    signer_client = RelayCommonsClient(NostrSdkTransport(relay.url, timeout=5))
    clients.append(signer_client)
    signer = ReceiptSigner(relay.journal, tmp_path / "signer.json", signer_client, operator)
    world = type("World", (), {})()
    world.relay, world.device, world.signer = relay, device, signer
    world.zebra_secret, world.secrets, world.certs = zebra_secret, secrets, certs
    world.operator_pubkey = keys.public_key(operator)
    try:
        yield world
    finally:
        for c in clients:
            await c.close()
        relay.remove()


async def _approve_receive(home: Device, rid: str) -> None:
    """Home is SUPERVISED for sharing: the owner approves the received workflow."""
    assert [t.task_definition_id for t in await home.pending(rid)] == ["receive_approval"]
    await home.answer(rid, "receive_approval", {"decision": "approve"})
    assert (await home.engine.store.load_process(rid)).state == ProcessState.COMPLETE


async def _skills_for(client: RelayCommonsClient, device_secret: str):
    return await client.fetch(
        [Filter(kinds=(SKILL_KIND,), recipients=(keys.public_key(device_secret),))]
    )


async def test_work_workflow_reaches_home_encrypted_with_receipts(world):
    home, work = world.device("home"), world.device("work")
    # Each device publishes its own cert; then work learns home's from the relay.
    assert await home.sync.publish_identity() == 1
    await work.sync.refresh()
    assert work.sync.other_spheres() == {"home": False}
    work.save(CHECKLIST)
    work.stats.runs["Code Review Checklist"] = 2
    [pid] = await work.share_all()
    await work.answer(pid, "observed_share_approval", {"decision": "approve"})
    assert [r["status"] for r in share_records(work.library)][-1] == "sent"

    [stored] = await _skills_for(home.sync.client, world.secrets["home"])
    assert stored.tag_values("enc") == ["nip44"] and ["-"] in stored.tags
    assert "Code Review" not in stored.content  # ciphertext on the relay

    [rid] = await home.receive()
    await _approve_receive(home, rid)
    received = home.library.commons_block("Code Review Checklist")
    assert (
        received["content_sha256"]
        == work.library.commons_block("Code Review Checklist")["content_sha256"]
    )
    assert received["tainted_by"] == ["work"]

    # The policy journalled both certs and the SKILL in order; the signer receipts each.
    kinds = [e["kind"] for e in world.relay.journal_entries()]
    assert kinds.count(SKILL_KIND) == 1 and len(kinds) == 3
    assert await world.signer.run_once() == 3
    receipts = await home.sync.client.fetch(
        [Filter(kinds=(RECEIPT_KIND,), authors=(world.operator_pubkey,))]
    )
    order = receipt_order(receipts, world.operator_pubkey)
    assert order[stored.id] == 3


async def test_relay_rejects_what_the_policy_forbids(world):
    home = world.device("home")
    stranger = keys.generate_secret_key()
    stranger_cert = make_device_cert(
        stranger, keys.public_key(world.secrets["home"]), label="x", sphere="x", observed=False
    )
    with pytest.raises(PublishRefused, match="not a registered Zebra key"):
        await home.sync.client.publish(stranger_cert)
    assert world.relay.journal_entries() == []


async def test_relay_outage_loses_nothing(world):
    home, work = world.device("home"), world.device("work")
    await home.sync.publish_identity()
    await work.sync.refresh()
    world.relay.stop()

    work.save(CHECKLIST)
    work.stats.runs["Code Review Checklist"] = 2
    [pid] = await work.share_all()
    await work.answer(pid, "observed_share_approval", {"decision": "approve"})
    assert len(work.sync.client.outbox) >= 1  # queued on disk (its cert and the SKILL)
    assert await home.receive() == []  # nothing yet, and no crash

    world.relay.resume()
    # Daemon ticks: the port answers a moment before strfry finishes starting.
    delivered, deadline = 0, time.time() + 20
    while not delivered and time.time() < deadline:
        delivered = await work.sync.flush()
        if not delivered:
            await asyncio.sleep(0.5)
    assert delivered >= 1
    assert len(work.sync.client.outbox) == 0
    [rid] = await home.receive()
    await _approve_receive(home, rid)
    assert home.library.commons_block("Code Review Checklist") is not None


async def test_revoked_device_rejected_by_receipt_order(world):
    home, work = world.device("home"), world.device("work")
    await home.sync.publish_identity()
    await work.sync.refresh()
    work.save(CHECKLIST)
    work.stats.runs["Code Review Checklist"] = 2
    [pid] = await work.share_all()
    await work.answer(pid, "observed_share_approval", {"decision": "approve"})
    [early] = await _skills_for(home.sync.client, world.secrets["home"])

    # The work laptop is lost: home (holding the Zebra key) revokes it on the relay.
    revoke = make_device_revoke(world.zebra_secret, keys.public_key(world.secrets["work"]))
    await home.sync.client.publish(revoke)
    assert await world.signer.run_once() == 4  # 2 certs, the SKILL, the revoke

    # The relay now refuses the revoked device outright.
    late = sign_event(
        world.secrets["work"], SKILL_KIND, [["p", "aa" * 32], COMMONS_TAG, ["-"]], "x"
    )
    with pytest.raises(PublishRefused, match="no valid cert"):
        await work.sync.client.publish(late)
    await home.sync.refresh([early])
    assert home.sync.receipts[early.id] < home.sync.receipts[revoke.id]
    # Stored before the revoke: still accepted by receipt order.
    assert home.sync.verify(early).ok
    # Without receipts (the S1 rule) the same event would be rejected.
    home.sync.receipt_pubkey = None
    assert home.sync.verify(early).reason == "revoked"


def test_retention_command_runs(world):
    done = world.relay.exec("delete", "--age=7776000", '--filter={"kinds":[1246],"#k":["4236"]}')
    assert done.returncode == 0, done.stderr[-500:]
    done = world.relay.exec("delete", "--age=7776000", '--filter={"kinds":[4236]}')
    assert done.returncode == 0, done.stderr[-500:]
