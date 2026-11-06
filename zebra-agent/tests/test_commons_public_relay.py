"""The public Commons relay's write policy, deploy files and receipt sidecar (#231).

``deploy/podman/commons-relay/write_policy.py`` runs inside the strfry container (stdlib Python
3.11); it is loaded here by path. The deploy tests check the deploy job never installs it.
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from zebra_agent.commons import keys, kinds
from zebra_agent.commons.events import COMMONS_TAG, PROTOCOL_VERSION_TAG, sign_event
from zebra_agent.commons.identity import make_device_cert, make_device_revoke
from zebra_agent.commons.receipts import main as receipts_main
from zebra_agent.commons.receipts import make_receipt, operator_secret_from_env

REPO = Path(__file__).resolve().parents[2]
RELAY_DIR = REPO / "deploy" / "podman" / "commons-relay"
POLICY = RELAY_DIR / "write_policy.py"
HASH = "ab" * 32


def _load_policy():
    spec = importlib.util.spec_from_file_location("zebra_commons_write_policy", POLICY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wp = _load_policy()


@pytest.fixture
def operator():
    return keys.generate_secret_key()


@pytest.fixture
def policy(tmp_path, operator):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"operator_pubkey": keys.public_key(operator)}))
    return wp.Policy(str(path), str(tmp_path / "receipts" / "journal.jsonl"))


def _req(event):
    return {"type": "new", "event": event.to_dict(), "sourceType": "IP4"}


def _offer(secret, *, d=HASH, x=HASH, extra=()):
    tags = [["d", d], ["x", x], ["zebra", "cd" * 32], COMMONS_TAG, PROTOCOL_VERSION_TAG, *extra]
    return sign_event(secret, kinds.OFFER_KIND, tags, "{}")


def _journal(policy):
    return [json.loads(line) for line in Path(policy.journal_path).read_text().splitlines()]


def test_any_zebras_offer_and_cert_are_accepted_and_journalled(policy):
    zebra, device = keys.generate_secret_key(), keys.generate_secret_key()
    cert = make_device_cert(
        zebra, keys.public_key(device), label="d", sphere="home", observed=False
    )
    offer = _offer(device)
    assert policy.decide(_req(cert)) == ("accept", "")
    assert policy.decide(_req(offer)) == ("accept", "")
    revoke = make_device_revoke(zebra, keys.public_key(device))
    assert policy.decide(_req(revoke)) == ("accept", "")
    assert [(e["seq"], e["id"]) for e in _journal(policy)] == [
        (1, cert.id),
        (2, offer.id),
        (3, revoke.id),
    ]


def test_only_public_kinds_tagged_zebra_commons(policy):
    secret = keys.generate_secret_key()
    tags = [COMMONS_TAG, PROTOCOL_VERSION_TAG]
    skill = sign_event(secret, kinds.SKILL_KIND, tags, "ciphertext")
    assert policy.decide(_req(skill))[1].startswith("blocked: SKILL")
    export = sign_event(secret, kinds.WORKFLOW_EXPORT_KIND, tags, "{}")
    assert policy.decide(_req(export)) == ("reject", "blocked: kind not accepted on this relay")
    note = sign_event(secret, 1, tags, "hello")
    assert policy.decide(_req(note))[0] == "reject"
    untagged = sign_event(secret, kinds.OFFER_KIND, [["d", HASH], ["x", HASH]], "{}")
    assert policy.decide(_req(untagged)) == ("reject", "blocked: not a Zebra Commons event")
    protected = _offer(secret, extra=(["-"],))
    assert policy.decide(_req(protected))[1].startswith("blocked: protected")
    assert not Path(policy.journal_path).exists()


@pytest.mark.parametrize("d,x", [(HASH, "cd" * 32), ("short", "short")])
def test_malformed_offer_is_refused(policy, d, x):
    offer = _offer(keys.generate_secret_key(), d=d, x=x)
    assert policy.decide(_req(offer)) == ("reject", "invalid: malformed OFFER")


def test_receipts_only_from_the_operator_and_not_journalled(policy, operator):
    assert policy.decide(_req(make_receipt(operator, 1, HASH, kinds.OFFER_KIND))) == ("accept", "")
    forged = make_receipt(keys.generate_secret_key(), 1, HASH, kinds.OFFER_KIND)
    assert policy.decide(_req(forged))[1] == "blocked: receipts come only from the relay operator"
    assert not Path(policy.journal_path).exists()


def test_no_policy_file_refuses_receipts_but_resends_keep_their_seq(tmp_path, operator):
    policy = wp.Policy(str(tmp_path / "missing.json"), str(tmp_path / "journal.jsonl"))
    assert policy.decide(_req(make_receipt(operator, 1, HASH, kinds.OFFER_KIND)))[0] == "reject"
    offer = _offer(keys.generate_secret_key())
    policy.decide(_req(offer))
    policy.decide(_req(offer))
    restarted = wp.Policy(policy.policy_path, policy.journal_path)
    other = _offer(keys.generate_secret_key(), d="ef" * 32, x="ef" * 32)
    restarted.decide(_req(other))
    assert [e["seq"] for e in _journal(restarted)] == [1, 2]


def test_policy_file_is_reread(policy, operator):
    path = Path(policy.policy_path)
    path.write_text("not json")
    os.utime(path, (1, 1))
    receipt = make_receipt(operator, 1, HASH, kinds.OFFER_KIND)
    assert policy.decide(_req(receipt))[0] == "reject"
    path.write_text(json.dumps({"operator_pubkey": keys.public_key(operator)}))
    os.utime(path, (2, 2))
    assert policy.decide(_req(receipt))[0] == "accept"


def test_plugin_speaks_strfry_jsonl(tmp_path):
    offer = _offer(keys.generate_secret_key())
    lines = [
        json.dumps({"type": "lookback", "event": offer.to_dict()}),
        json.dumps(_req(offer)),
        json.dumps(_req(sign_event(keys.generate_secret_key(), 1, [COMMONS_TAG], "x"))),
    ]
    env = {
        **os.environ,
        "ZEBRA_COMMONS_POLICY": str(tmp_path / "policy.json"),
        "ZEBRA_COMMONS_JOURNAL": str(tmp_path / "j" / "journal.jsonl"),
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
    assert answers[0]["id"] == offer.id


# --- receipt sidecar ---------------------------------------------------------------------


def test_sidecar_reads_its_secret_from_the_named_variable(capsys):
    secret = keys.generate_secret_key()
    env = {"ZEBRA_COMMONS_OPERATOR_SECRET": keys.nsec_encode(secret)}
    assert operator_secret_from_env(env, "ZEBRA_COMMONS_OPERATOR_SECRET") == secret
    with pytest.raises(ValueError, match="ZEBRA_SYNC_OPERATOR_SECRET is not set"):
        operator_secret_from_env(env)
    receipts_main(["--keygen", "--secret-env", "ZEBRA_COMMONS_OPERATOR_SECRET"])
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("ZEBRA_COMMONS_OPERATOR_SECRET=nsec1")
    assert re.fullmatch(r"ZEBRA_COMMONS_RECEIPT_PUBKEY=[0-9a-f]{64}", out[1])


# --- not deployed ------------------------------------------------------------------------


def test_deploy_job_never_installs_the_public_relay():
    deploy = (REPO / "scripts" / "deploy-podman.sh").read_text()
    installs = re.findall(r"install -m \d+ (\S+)", deploy)
    assert installs and all("deploy/podman/quadlet/" in p or "commons" not in p for p in installs)
    assert "commons-relay" not in deploy and "zebra-commons" not in deploy
    quadlet = {p.name for p in (REPO / "deploy" / "podman" / "quadlet").iterdir()}
    assert not {n for n in quadlet if "commons" in n}
    ci = (REPO / ".gitlab-ci.yml").read_text()
    assert "commons-relay" not in ci and "zebra-commons-relay" not in ci


def test_public_relay_units_are_in_the_repo_and_separate_from_the_private_relay():
    names = {p.name for p in RELAY_DIR.iterdir()}
    assert {
        "zebra-commons-relay.container",
        "zebra-commons-receipts.container",
        "zebra-commons.network",
        "strfry.conf",
        "policy.json.example",
        "write_policy.py",
    } <= names
    relay = (RELAY_DIR / "zebra-commons-relay.container").read_text()
    assert "127.0.0.1:7779:7777" in relay and ":8000" not in relay
    assert "zebra-sync" not in relay
    conf = (RELAY_DIR / "strfry.conf").read_text()
    auth = conf[conf.index("auth {") : conf.index("}", conf.index("auth {"))]
    assert "enabled = false" in auth  # public reads, no NIP-42
    assert '"/etc/zebra-commons/write_policy.py"' in conf
    receipts = (RELAY_DIR / "zebra-commons-receipts.container").read_text()
    assert "--secret-env ZEBRA_COMMONS_OPERATOR_SECRET" in receipts
    assert "SECRET=" not in receipts  # the secret lives only in commons-operator.env
    assert "zebra-commons-relay:7777" in receipts
