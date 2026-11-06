"""The private sync relay's write policy and deploy files (#246).

``deploy/podman/sync-relay/write_policy.py`` runs inside the strfry container (stdlib Python
3.11); it is loaded here by path. The last tests check the deploy job never installs the relay.
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from zebra_agent.commons import keys
from zebra_agent.commons.client import SKILL_KIND
from zebra_agent.commons.events import COMMONS_TAG, sign_event
from zebra_agent.commons.identity import make_device_cert, make_device_revoke
from zebra_agent.commons.receipts import make_receipt

REPO = Path(__file__).resolve().parents[2]
RELAY_DIR = REPO / "deploy" / "podman" / "sync-relay"
POLICY = RELAY_DIR / "write_policy.py"


def _load_policy():
    spec = importlib.util.spec_from_file_location("zebra_sync_write_policy", POLICY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wp = _load_policy()


@pytest.fixture
def ids():
    zebra = keys.generate_secret_key()
    return {
        "zebra": zebra,
        "device": keys.generate_secret_key(),
        "operator": keys.generate_secret_key(),
    }


@pytest.fixture
def policy(tmp_path, ids):
    allow = tmp_path / "allowlist.json"
    allow.write_text(
        json.dumps(
            {
                "zebra_pubkeys": [keys.public_key(ids["zebra"])],
                "operator_pubkey": keys.public_key(ids["operator"]),
            }
        )
    )
    return wp.Policy(str(allow), str(tmp_path / "receipts" / "journal.jsonl"))


def _req(event, authed=None):
    request = {"type": "new", "event": event.to_dict(), "sourceType": "IP4"}
    if authed:
        request["authed"] = authed
    return request


def _skill(device, protected=True):
    tags = [["p", "aa" * 32], COMMONS_TAG] + ([["-"]] if protected else [])
    return sign_event(device, SKILL_KIND, tags, "ciphertext")


def _cert(ids, **kw):
    return make_device_cert(
        ids["zebra"], keys.public_key(ids["device"]), label="d", sphere="home", observed=False, **kw
    )


def _journal(policy):
    return [json.loads(line) for line in Path(policy.journal_path).read_text().splitlines()]


def test_cert_then_protected_authenticated_skill_is_accepted_and_journalled(policy, ids):
    device_pub = keys.public_key(ids["device"])
    skill = _skill(ids["device"])
    assert policy.decide(_req(skill, authed=device_pub))[0] == "reject"  # no cert yet

    cert = _cert(ids)
    assert policy.decide(_req(cert)) == ("accept", "")
    assert policy.decide(_req(skill, authed=device_pub)) == ("accept", "")
    assert [(e["seq"], e["id"]) for e in _journal(policy)] == [(1, cert.id), (2, skill.id)]


def test_skill_must_be_protected_and_authenticated_as_its_author(policy, ids):
    policy.decide(_req(_cert(ids)))
    device_pub = keys.public_key(ids["device"])
    action, msg = policy.decide(_req(_skill(ids["device"], protected=False), authed=device_pub))
    assert (action, msg.split(":")[0]) == ("reject", "blocked")
    action, msg = policy.decide(_req(_skill(ids["device"])))
    assert (action, msg.split(":")[0]) == ("reject", "auth-required")
    other = keys.public_key(keys.generate_secret_key())
    assert policy.decide(_req(_skill(ids["device"]), authed=other))[0] == "reject"


def test_unregistered_zebra_and_other_kinds_are_rejected(policy, ids):
    stranger = keys.generate_secret_key()
    foreign_cert = make_device_cert(
        stranger, keys.public_key(ids["device"]), label="d", sphere="x", observed=False
    )
    assert policy.decide(_req(foreign_cert))[1].startswith("blocked:")
    note = sign_event(ids["device"], 1, [COMMONS_TAG], "hello")
    assert policy.decide(_req(note)) == ("reject", "blocked: kind not accepted on this relay")
    untagged = sign_event(ids["device"], SKILL_KIND, [["-"]], "x")
    assert policy.decide(_req(untagged))[1] == "blocked: not a Zebra Commons event"
    assert not Path(policy.journal_path).exists()


def test_revoked_and_expired_devices_cannot_publish(policy, ids):
    device_pub = keys.public_key(ids["device"])
    policy.decide(_req(_cert(ids)))
    policy.decide(_req(make_device_revoke(ids["zebra"], device_pub)))
    assert policy.decide(_req(_skill(ids["device"]), authed=device_pub))[0] == "reject"

    other = {**ids, "device": keys.generate_secret_key()}
    policy.decide(_req(_cert(other, expires_at=1)))
    other_pub = keys.public_key(other["device"])
    assert policy.decide(_req(_skill(other["device"]), authed=other_pub))[0] == "reject"


def test_receipts_only_from_the_operator_and_not_journalled(policy, ids):
    receipt = make_receipt(ids["operator"], 1, "ab" * 32, SKILL_KIND)
    assert policy.decide(_req(receipt)) == ("accept", "")
    forged = make_receipt(ids["zebra"], 1, "ab" * 32, SKILL_KIND)
    assert policy.decide(_req(forged))[0] == "reject"
    assert not Path(policy.journal_path).exists()


def test_resend_keeps_its_seq_and_state_survives_a_restart(policy, ids, tmp_path):
    cert = _cert(ids)
    policy.decide(_req(cert))
    policy.decide(_req(cert))  # an offline-queue resend
    assert len(_journal(policy)) == 1

    restarted = wp.Policy(policy.allowlist_path, policy.journal_path)
    device_pub = keys.public_key(ids["device"])
    skill = _skill(ids["device"])
    assert restarted.decide(_req(skill, authed=device_pub)) == ("accept", "")
    assert _journal(restarted)[-1]["seq"] == 2


def test_allow_list_is_reread_and_fails_closed(policy, ids):
    cert = _cert(ids)
    allow = Path(policy.allowlist_path)
    allow.write_text("not json")
    os.utime(allow, (1, 1))
    assert policy.decide(_req(cert))[0] == "reject"
    allow.write_text(json.dumps({"zebra_pubkeys": [keys.public_key(ids["zebra"])]}))
    os.utime(allow, (2, 2))
    assert policy.decide(_req(cert))[0] == "accept"
    allow.unlink()
    assert policy.decide(_req(_cert(ids, expires_at=2**40)))[0] == "reject"


def test_plugin_speaks_strfry_jsonl(tmp_path, ids):
    allow = tmp_path / "allowlist.json"
    allow.write_text(json.dumps({"zebra_pubkeys": [keys.public_key(ids["zebra"])]}))
    cert = _cert(ids)
    lines = [
        json.dumps({"type": "lookback", "event": cert.to_dict()}),
        json.dumps(_req(cert)),
        json.dumps(_req(sign_event(ids["device"], 1, [COMMONS_TAG], "x"))),
    ]
    env = {
        **os.environ,
        "ZEBRA_SYNC_ALLOWLIST": str(allow),
        "ZEBRA_SYNC_JOURNAL": str(tmp_path / "j" / "journal.jsonl"),
    }
    out = subprocess.run(
        [sys.executable, "-I", str(POLICY)],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=True,
    )
    answers = [json.loads(line) for line in out.stdout.splitlines()]
    assert [a["action"] for a in answers] == ["accept", "reject"]
    assert answers[0]["id"] == cert.id


def test_policy_kinds_match_the_commons_code():
    from zebra_agent.commons.identity import DEVICE_CERT_KIND, DEVICE_REVOKE_KIND
    from zebra_agent.commons.receipts import RECEIPT_KIND

    assert (wp.SKILL_KIND, wp.DEVICE_CERT_KIND, wp.DEVICE_REVOKE_KIND, wp.RECEIPT_KIND) == (
        SKILL_KIND,
        DEVICE_CERT_KIND,
        DEVICE_REVOKE_KIND,
        RECEIPT_KIND,
    )


# --- not deployed ----------------------------------------------------------------------


def test_deploy_job_never_installs_the_relay():
    deploy = (REPO / "scripts" / "deploy-podman.sh").read_text()
    installs = re.findall(r"install -m \d+ (\S+)", deploy)
    assert '"$REPO_ROOT"/deploy/podman/quadlet/*.container' in installs
    assert not any("sync-relay" in path for path in installs)
    assert "sync-relay" not in deploy and "zebra-sync" not in deploy
    quadlet = {p.name for p in (REPO / "deploy" / "podman" / "quadlet").iterdir()}
    assert not {n for n in quadlet if "sync" in n}
    ci = (REPO / ".gitlab-ci.yml").read_text()
    assert "sync-relay" not in ci and "zebra-sync" not in ci


def test_relay_units_are_in_the_repo():
    names = {p.name for p in RELAY_DIR.iterdir()}
    assert {
        "zebra-sync-relay.container",
        "zebra-sync-receipts.container",
        "zebra-sync.network",
        "zebra-sync-retention.service",
        "zebra-sync-retention.timer",
        "strfry.conf",
        "allowlist.json.example",
        "write_policy.py",
    } <= names
    relay = (RELAY_DIR / "zebra-sync-relay.container").read_text()
    assert "127.0.0.1:7778:7777" in relay and ":8000" not in relay
    retention = (RELAY_DIR / "zebra-sync-retention.service").read_text()
    assert "--age=7776000" in retention  # 90 days
    receipts = (RELAY_DIR / "zebra-sync-receipts.container").read_text()
    assert "SECRET=" not in receipts  # the operator secret lives only in sync-operator.env
