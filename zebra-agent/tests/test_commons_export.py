"""Commons S2b (#229): signed export files, verification, adoption and ``c:`` ids."""

from __future__ import annotations

import hashlib
import json

import pytest

from zebra_agent.commons import keys
from zebra_agent.commons.events import sign_event
from zebra_agent.commons.export import (
    ExportRefused,
    adopt_export,
    build_export,
    dump_export,
    export_workflow,
    verify_export,
)
from zebra_agent.commons.identity import make_device_cert, make_device_revoke
from zebra_agent.library import LLM_DEFINED_TAG, AdoptionRefused, WorkflowLibrary
from zebra_agent.provenance import content_sha256, read_commons, with_commons

WORKFLOW = """name: "Project Update"
description: "Update a project plan"
tags: [planning]
version: 1
first_task: step1
tasks:
  step1:
    name: "Step"
    action: llm_call
    auto: true
    properties:
      prompt: |
        Update the plan.
        Goal: {{goal}}
routings: []
"""


@pytest.fixture
def zebra():
    secret = keys.generate_secret_key()
    return secret, keys.public_key(secret)


@pytest.fixture
def device(zebra):
    z_sec, _ = zebra
    secret = keys.generate_secret_key()
    cert = make_device_cert(
        z_sec, keys.public_key(secret), label="Home", sphere="home", observed=False
    )
    return secret, cert


@pytest.fixture
def home(tmp_path):
    return WorkflowLibrary(tmp_path / "home", owner_user_id=1, sphere="home")


@pytest.fixture
def work(tmp_path):
    return WorkflowLibrary(tmp_path / "work", owner_user_id=7, sphere="work")


async def _export(library, zebra, device, name="Project Update") -> str:
    _, z_pub = zebra
    d_sec, cert = device
    return await export_workflow(
        library, name, device_secret=d_sec, zebra_pubkey=z_pub, chain=[cert]
    )


# ---------------------------------------------------------------------------
# Export and verification (O2)
# ---------------------------------------------------------------------------


class TestExport:
    async def test_export_verifies_and_names_the_zebra(self, home, zebra, device):
        home.add_workflow(WORKFLOW, llm_defined=True)
        text = await _export(home, zebra, device)
        result = verify_export(text)
        assert result.ok and result.reason == "ok"
        assert result.zebra_pubkey == zebra[1]
        assert result.signer_pubkey == keys.public_key(device[0])
        assert result.name == "Project Update"
        assert result.content_sha256 == content_sha256(WORKFLOW)
        assert result.commons["content_sha256"] == result.content_sha256
        # The block and local tags stay home; the content (and so the hash) travels.
        assert "commons:" not in result.yaml
        assert LLM_DEFINED_TAG not in result.yaml
        assert verify_export(text, expected_zebra=zebra[1]).ok
        assert verify_export(text.encode()).ok

    async def test_every_single_byte_change_fails(self, home, zebra, device):
        home.add_workflow(WORKFLOW)
        raw = (await _export(home, zebra, device)).encode()
        for i in range(len(raw)):
            tampered = bytearray(raw)
            tampered[i] ^= 0x01
            assert not verify_export(bytes(tampered)).ok, f"byte {i} accepted"

    async def test_signed_content_change_fails_signature(self, home, zebra, device):
        home.add_workflow(WORKFLOW)
        data = json.loads(await _export(home, zebra, device))
        data["event"]["content"] = data["event"]["content"].replace("Update the plan", "Wipe it")
        assert verify_export(dump_export(data)).reason == "bad_signature"

    async def test_whitespace_only_change_is_not_canonical(self, home, zebra, device):
        home.add_workflow(WORKFLOW)
        text = await _export(home, zebra, device)
        assert verify_export(text.replace("\n", "\r\n", 1)).reason == "not_canonical"
        assert verify_export(text + "\n").reason == "not_canonical"

    async def test_wrong_zebra_is_refused(self, home, zebra, device):
        home.add_workflow(WORKFLOW)
        text = await _export(home, zebra, device)
        other = keys.public_key(keys.generate_secret_key())
        assert verify_export(text, expected_zebra=other).reason == "wrong_zebra"

    async def test_revoked_device_fails(self, home, zebra, device):
        home.add_workflow(WORKFLOW)
        text = await _export(home, zebra, device)
        revoke = make_device_revoke(zebra[0], keys.public_key(device[0]), reason="lost")
        assert verify_export(text, revocations=[revoke]).reason == "revoked"

    async def test_uncertified_device_cannot_export_or_verify(self, home, zebra, device):
        home.add_workflow(WORKFLOW)
        with pytest.raises(ExportRefused, match="not attributed"):
            await export_workflow(
                home, "Project Update", device_secret=device[0], zebra_pubkey=zebra[1], chain=[]
            )
        data = json.loads(await _export(home, zebra, device))
        data["chain"] = []
        assert verify_export(dump_export(data)).reason == "no_cert"

    async def test_chain_cert_from_another_key_is_bad_chain(self, home, zebra, device):
        home.add_workflow(WORKFLOW)
        data = json.loads(await _export(home, zebra, device))
        rogue = make_device_cert(
            keys.generate_secret_key(),
            keys.public_key(device[0]),
            label="x",
            sphere="home",
            observed=False,
        )
        data["chain"].append(rogue.to_dict())
        assert verify_export(dump_export(data)).reason == "bad_chain"

    async def test_expired_cert_fails(self, home, zebra, device):
        home.add_workflow(WORKFLOW)
        cert = make_device_cert(
            zebra[0],
            keys.public_key(device[0]),
            label="H",
            sphere="home",
            observed=False,
            expires_at=2_000_000_000,
        )
        text = await export_workflow(
            home, "Project Update", device_secret=device[0], zebra_pubkey=zebra[1], chain=[cert]
        )
        assert verify_export(text).ok
        assert verify_export(text, now=2_000_000_001).reason == "expired"

    def test_hash_mismatch_signed_by_a_valid_device_fails(self, zebra, device):
        # A device that signs a block whose hash does not match the YAML is still refused.
        d_sec, cert = device
        block = {"content_sha256": "0" * 64, "foreign_users": False}
        content = json.dumps({"name": "X", "yaml": WORKFLOW, "commons": block}, sort_keys=True)
        event = sign_event(
            d_sec, 31229, [["x", "0" * 64], ["zebra", zebra[1]], ["t", "zebra-commons"]], content
        )
        data = {
            "format": "zebra-workflow-export",
            "version": 1,
            "event": event.to_dict(),
            "chain": [cert.to_dict()],
        }
        assert verify_export(dump_export(data)).reason == "hash_mismatch"

    def test_foreign_block_signed_by_a_valid_device_fails(self, zebra, device):
        d_sec, cert = device
        digest = content_sha256(WORKFLOW)
        block = {"content_sha256": digest, "foreign_users": True}
        content = json.dumps({"name": "X", "yaml": WORKFLOW, "commons": block}, sort_keys=True)
        event = sign_event(d_sec, 31229, [["x", digest], ["zebra", zebra[1]]], content)
        data = {
            "format": "zebra-workflow-export",
            "version": 1,
            "event": event.to_dict(),
            "chain": [cert.to_dict()],
        }
        assert verify_export(dump_export(data)).reason == "foreign_users"

    @pytest.mark.parametrize("text", ["", "not json", "[]", '{"format": "x"}'])
    def test_malformed_files(self, text):
        assert not verify_export(text).ok

    async def test_unknown_workflow_is_refused(self, home, zebra, device):
        with pytest.raises(ExportRefused, match="no active workflow"):
            await _export(home, zebra, device, name="Nope")

    async def test_system_workflow_is_refused(self, home, zebra, device):
        home.add_workflow(WORKFLOW.replace("tags: [planning]", "tags: [planning, system]"))
        with pytest.raises(ExportRefused, match="may not leave"):
            await _export(home, zebra, device)

    async def test_foreign_workflow_is_refused(self, home, zebra, device):
        home.add_workflow(WORKFLOW, writer="creator", exposure={"user_ids": [2]})
        with pytest.raises(ExportRefused, match="may not leave"):
            await _export(home, zebra, device)

    async def test_blockless_workflow_is_refused(self, home, zebra, device):
        home.ensure_initialized()
        (home.library_path / "project_update.yaml").write_text(WORKFLOW)
        with pytest.raises(ExportRefused, match="may not leave"):
            await _export(home, zebra, device)

    def test_build_refuses_a_block_whose_hash_is_stale(self, zebra, device):
        stale = with_commons(WORKFLOW, {"content_sha256": "f" * 64, "foreign_users": False})
        with pytest.raises(ExportRefused, match="does not match"):
            build_export(stale, device_secret=device[0], zebra_pubkey=zebra[1], chain=[device[1]])


# ---------------------------------------------------------------------------
# Adoption (O3) and definition ids (O1): the issue's E2E
# ---------------------------------------------------------------------------


class TestAdopt:
    async def test_export_verify_adopt_keeps_hash_and_lineage(self, home, work, zebra, device):
        home.add_workflow(WORKFLOW, llm_defined=True)
        home.add_workflow(
            WORKFLOW.replace("Update the plan.", "Revise the plan."), llm_defined=True
        )
        sent = read_commons(next(f for f in home._files_named("Project Update")).read_text())
        text = await _export(home, zebra, device)

        verified = verify_export(text)
        assert verified.ok
        path = adopt_export(work, verified, name="Project Update (from Home)")

        saved = path.read_text()
        block = read_commons(saved)
        assert block["content_sha256"] == sent["content_sha256"] == content_sha256(saved)
        assert block["parent_sha256"] == sent["parent_sha256"] is not None
        assert block["ancestors"] == sent["ancestors"]
        assert block["tainted_by"] == sent["tainted_by"]
        assert block["foreign_users"] is False
        assert block["supervised"] is True
        assert block["share_with"] == []
        assert block["sphere"] == "work"
        assert block["adopted_at"]
        assert block["origin_pubkey"] == zebra[1]
        assert LLM_DEFINED_TAG not in saved
        assert "planning" in saved

        # Loads and gets a content-addressed id distinct from a same-named local workflow.
        adopted = work.get_workflow("Project Update (from Home)")
        digest = hashlib.sha256(
            f"{block['content_sha256']}:Project Update (from Home)".encode()
        ).hexdigest()
        assert adopted.id == f"c:{digest[:16]}"
        assert adopted.id != home.get_workflow("Project Update").id
        assert [w.name for w in await work.list_workflows()] == ["Project Update (from Home)"]

    async def test_adopt_under_original_name_still_differs_from_local_id(
        self, home, work, zebra, device
    ):
        home.add_workflow(WORKFLOW)
        work.add_workflow(WORKFLOW.replace("Update the plan.", "Local plan."))
        verified = verify_export(await _export(home, zebra, device))
        with pytest.raises(AdoptionRefused, match="already named"):
            adopt_export(work, verified)
        assert len(work._files_named("Project Update")) == 1
        adopt_export(work, verified, name="Project Update (from Home)")
        ids = {work.get_workflow(n).id for n in ("Project Update", "Project Update (from Home)")}
        assert len(ids) == 2

    async def test_readopting_is_idempotent(self, home, work, zebra, device):
        home.add_workflow(WORKFLOW)
        verified = verify_export(await _export(home, zebra, device))
        first = adopt_export(work, verified, name="PU")
        assert adopt_export(work, verified, name="PU") == first
        assert len(list(work.library_path.glob("*.yaml"))) == 1

    def test_hash_mismatch_writes_nothing(self, work):
        block = {"content_sha256": "0" * 64, "foreign_users": False}
        with pytest.raises(AdoptionRefused, match="does not match"):
            work.save(WORKFLOW, writer="adopt", received=block, expected_sha256="0" * 64)
        digest = content_sha256(WORKFLOW)
        good = {"content_sha256": digest, "foreign_users": False}
        with pytest.raises(AdoptionRefused, match="offered hash"):
            work.save(WORKFLOW, writer="adopt", received=good, expected_sha256="1" * 64)
        with pytest.raises(AdoptionRefused, match="no received"):
            work.save(WORKFLOW, writer="adopt", expected_sha256=digest)
        with pytest.raises(AdoptionRefused, match="foreign_users"):
            work.save(
                WORKFLOW,
                writer="adopt",
                received={**good, "foreign_users": True},
                expected_sha256=digest,
            )
        with pytest.raises(AdoptionRefused, match="never llm-defined"):
            work.save(
                WORKFLOW, writer="adopt", received=good, expected_sha256=digest, llm_defined=True
            )
        assert not list(work.library_path.glob("*.yaml"))

    def test_received_block_is_kept_not_recomputed(self, work):
        digest = content_sha256(WORKFLOW)
        received = {
            "content_sha256": digest,
            "parent_sha256": "a" * 64,
            "ancestors": ["a" * 64, "b" * 64],
            "origin_pubkey": "c" * 64,
            "fork_of": None,
            "adopted_at": None,
            "supervised": False,
            "sphere": "home",
            "tainted_by": ["home", "work"],
            "share_with": ["public"],
            "foreign_users": False,
        }
        path = work.save(
            WORKFLOW.replace("tags: [planning]", "tags: [planning, llm-defined]"),
            writer="adopt",
            received=received,
            expected_sha256=digest,
            origin_pubkey="d" * 64,
        )
        assert LLM_DEFINED_TAG not in path.read_text()  # the sender's local tag is dropped
        block = read_commons(path.read_text())
        assert block["content_sha256"] == digest
        assert block["parent_sha256"] == "a" * 64
        assert block["origin_pubkey"] == "c" * 64  # kept: the original publisher
        assert block["ancestors"] == ["a" * 64, "b" * 64]
        assert block["tainted_by"] == ["home", "work"]
        assert block["share_with"] == []
        assert block["sphere"] == "work"

    def test_other_writers_reject_adoption_arguments(self, work):
        with pytest.raises(ValueError, match="only for writer='adopt'"):
            work.save(WORKFLOW, writer="human", expected_sha256="x")

    def test_local_save_of_an_adopted_workflow_is_a_local_change(self, work):
        digest = content_sha256(WORKFLOW)
        work.save(
            WORKFLOW,
            writer="adopt",
            received={"content_sha256": digest, "foreign_users": False, "tainted_by": ["home"]},
            expected_sha256=digest,
        )
        path = work.save(WORKFLOW.replace("Update the plan.", "Edited."), writer="human")
        block = read_commons(path.read_text())
        assert block["parent_sha256"] == digest
        assert block["supervised"] is True
        assert block["tainted_by"] == ["home", "work"]


# ---------------------------------------------------------------------------
# Signed display name and golden tasks for the importer (#230)
# ---------------------------------------------------------------------------


async def test_export_carries_signed_display_name_and_golden_tasks(home, zebra, device, tmp_path):
    golden = tmp_path / "golden"
    golden.mkdir()
    (golden / "g.yaml").write_text(
        "id: g1\nworkflow: Project Update\ngoal: Update the launch plan\n"
        "expected: A plan\ncriteria: [Lists steps]\n"
    )
    home.golden_path = golden
    home.add_workflow(WORKFLOW)
    _, z_pub = zebra
    d_sec, cert = device
    text = await export_workflow(
        home,
        "Project Update",
        device_secret=d_sec,
        zebra_pubkey=z_pub,
        chain=[cert],
        display_name="Home Zebra",
        with_golden=True,
    )
    result = verify_export(text)
    assert result.ok and result.display_name == "Home Zebra"
    assert result.golden_tasks == [
        {"goal": "Update the launch plan", "expected": "A plan", "criteria": ["Lists steps"]}
    ]
    plain = verify_export(await _export(home, zebra, device))
    assert plain.display_name is None and plain.golden_tasks == []
