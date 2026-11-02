"""Tests for workflow provenance and the library's one save path (#229, S2a)."""

import pytest
import yaml

from zebra_agent.commons import commons_exportable
from zebra_agent.library import LeakGuardRejected, WorkflowLibrary
from zebra_agent.provenance import (
    ANCESTOR_WINDOW,
    Exposure,
    NotHashableError,
    canonical_content,
    content_sha256,
    has_foreign_users,
    next_block,
    read_commons,
    strip_commons,
    try_content_sha256,
    with_commons,
)

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
      prompt: "Update the plan: {{goal}}"
"""


def _changed(prompt: str = "Rewrite the plan: {{goal}}") -> str:
    return WORKFLOW.replace("Update the plan: {{goal}}", prompt)


@pytest.fixture
def library(tmp_path):
    return WorkflowLibrary(tmp_path / "workflows", owner_user_id=1, sphere="home")


def _block(path) -> dict:
    return read_commons(path.read_text())


# ---------------------------------------------------------------------------
# Canonical hash (O2)
# ---------------------------------------------------------------------------


class TestCanonicalHash:
    def test_rename_does_not_change_the_hash(self):
        renamed = WORKFLOW.replace('name: "Project Update"', 'name: "Project Update (from Bob)"')
        assert content_sha256(renamed) == content_sha256(WORKFLOW)

    def test_local_tags_do_not_change_the_hash(self):
        tagged = WORKFLOW.replace("tags: [planning]", "tags: [planning, llm-defined, system]")
        assert content_sha256(tagged) == content_sha256(WORKFLOW)

    def test_no_tags_and_only_local_tags_hash_the_same(self):
        none = WORKFLOW.replace("tags: [planning]\n", "")
        local = WORKFLOW.replace("tags: [planning]", "tags: [llm-defined]")
        empty = WORKFLOW.replace("tags: [planning]", "tags: []")
        assert content_sha256(none) == content_sha256(local) == content_sha256(empty)

    def test_redumped_yaml_hashes_the_same(self):
        redumped = yaml.safe_dump(yaml.safe_load(WORKFLOW), sort_keys=True, width=40)
        assert content_sha256(redumped) == content_sha256(WORKFLOW)

    def test_commons_block_is_not_hashed(self):
        stamped = with_commons(WORKFLOW, {"content_sha256": "x", "share_with": ["public"]})
        assert content_sha256(stamped) == content_sha256(WORKFLOW)

    def test_date_like_string_stays_a_string(self):
        dated = WORKFLOW.replace("version: 1", "version: 1\nsince: 2026-01-01")
        assert canonical_content(dated)["since"] == "2026-01-01"
        assert content_sha256(dated) != content_sha256(WORKFLOW)

    def test_content_change_changes_the_hash(self):
        assert content_sha256(_changed()) != content_sha256(WORKFLOW)

    def test_hash_is_sha256_hex(self):
        digest = content_sha256(WORKFLOW)
        assert len(digest) == 64 and int(digest, 16) >= 0

    @pytest.mark.parametrize(
        "extra, reason",
        [
            ("odd: {1: one}", "non-string key"),
            ("blob: !!binary aGVsbG8=", "bytes"),
            ("ratio: .nan", "non-finite"),
            ("items: !!set {a: null}", "set value"),
        ],
    )
    def test_unhashable_yaml_has_a_reason(self, extra, reason):
        with pytest.raises(NotHashableError, match=reason):
            content_sha256(WORKFLOW + extra + "\n")
        assert try_content_sha256(WORKFLOW + extra + "\n")[0] is None


# ---------------------------------------------------------------------------
# The block on disk
# ---------------------------------------------------------------------------


class TestBlockText:
    def test_strip_keeps_the_rest_byte_for_byte(self):
        commented = "# a comment\n" + WORKFLOW
        stamped = with_commons(commented, {"content_sha256": "abc"})
        assert strip_commons(stamped) == commented

    def test_strip_of_a_block_in_the_middle(self):
        text = 'name: "X"\ncommons:\n  content_sha256: abc\n  share_with: [public]\nversion: 2\n'
        assert yaml.safe_load(strip_commons(text)) == {"name": "X", "version": 2}

    def test_block_is_the_last_key_with_every_field(self):
        stamped = with_commons(WORKFLOW, {"content_sha256": "abc"})
        data = yaml.safe_load(stamped)
        assert list(data)[-1] == "commons"
        assert data["commons"]["content_sha256"] == "abc"
        assert data["commons"]["origin_pubkey"] is None
        assert "foreign_users" in data["commons"]


# ---------------------------------------------------------------------------
# Local-change rules (O3)
# ---------------------------------------------------------------------------


class TestNextBlock:
    def test_new_workflow(self):
        block = next_block(
            new_hash="h1",
            parent_block=None,
            parent_hash=None,
            has_parent=False,
            sphere="home",
            foreign=False,
        )
        assert block["content_sha256"] == "h1"
        assert block["parent_sha256"] is None and block["ancestors"] == []
        assert block["sphere"] == "home" and block["tainted_by"] == ["home"]
        assert block["share_with"] == [] and block["foreign_users"] is False

    def test_change_records_lineage_and_resets_sharing(self):
        parent = {
            "content_sha256": "h1",
            "parent_sha256": "h0",
            "ancestors": ["h0"],
            "origin_pubkey": "npub-publisher",
            "supervised": True,
            "sphere": "home",
            "tainted_by": ["home"],
            "share_with": ["public"],
            "foreign_users": False,
        }
        block = next_block(
            new_hash="h2",
            parent_block=parent,
            parent_hash="h1",
            has_parent=True,
            sphere="work",
            foreign=False,
        )
        assert block["parent_sha256"] == "h1"
        assert block["ancestors"] == ["h1", "h0"]
        assert block["origin_pubkey"] is None
        assert block["share_with"] == []
        assert block["supervised"] is True
        assert block["sphere"] == "home"
        assert block["tainted_by"] == ["home", "work"]

    def test_ancestors_are_capped_and_deduplicated(self):
        parent = {
            "content_sha256": "p",
            "ancestors": ["p"] + [f"a{i}" for i in range(40)],
        }
        block = next_block(
            new_hash="n",
            parent_block=parent,
            parent_hash="p",
            has_parent=True,
            sphere="home",
            foreign=False,
        )
        assert len(block["ancestors"]) == ANCESTOR_WINDOW
        assert block["ancestors"][:2] == ["p", "a0"]
        assert block["ancestors"].count("p") == 1

    def test_unchanged_content_keeps_the_block(self):
        parent = {"content_sha256": "h1", "ancestors": ["h0"], "share_with": ["home"]}
        block = next_block(
            new_hash="h1",
            parent_block=parent,
            parent_hash="h1",
            has_parent=True,
            sphere="work",
            foreign=False,
        )
        assert block["share_with"] == ["home"] and block["ancestors"] == ["h0"]

    def test_foreign_users_only_grows(self):
        block = next_block(
            new_hash="h2",
            parent_block={"content_sha256": "h1", "foreign_users": True},
            parent_hash="h1",
            has_parent=True,
            sphere="home",
            foreign=False,
        )
        assert block["foreign_users"] is True

    def test_unknown_owner_fails_closed(self):
        assert has_foreign_users([1], None) is True
        assert has_foreign_users([], None) is False
        assert has_foreign_users([1], 1) is False
        assert has_foreign_users([1, 2], 1) is True


# ---------------------------------------------------------------------------
# WorkflowLibrary.save (O1, O3, O4, O5)
# ---------------------------------------------------------------------------


class TestLibrarySave:
    def test_add_workflow_stamps_a_block(self, library):
        library.add_workflow(WORKFLOW)
        (path,) = library.library_path.glob("*.yaml")
        block = _block(path)
        assert block["content_sha256"] == content_sha256(WORKFLOW)
        assert block["sphere"] == "home" and block["tainted_by"] == ["home"]
        assert block["parent_sha256"] is None

    def test_an_incoming_block_is_ignored(self, library):
        forged = with_commons(
            WORKFLOW, {"content_sha256": "forged", "share_with": ["public"], "foreign_users": False}
        )
        path = library.save(
            forged, writer="optimizer", exposure=Exposure(user_ids=[2], reject=True)
        )
        block = _block(path)
        assert block["content_sha256"] == content_sha256(WORKFLOW)
        assert block["share_with"] == []
        assert block["foreign_users"] is True

    def test_a_rewrite_of_an_old_file_takes_its_hash_as_parent(self, library):
        library.ensure_initialized()
        (library.library_path / "project_update.yaml").write_text(WORKFLOW)  # pre-#229 file
        path = library.save(_changed(), writer="optimizer", llm_defined=True)
        block = _block(path)
        assert path.name == "project_update_1.yaml"
        assert block["parent_sha256"] == content_sha256(WORKFLOW)
        assert block["ancestors"] == [content_sha256(WORKFLOW)]
        assert "llm-defined" in yaml.safe_load(path.read_text())["tags"]

    def test_lineage_across_three_versions(self, library):
        library.add_workflow(WORKFLOW)
        library.save(_changed("v2: {{goal}}"), writer="optimizer")
        path = library.save(_changed("v3: {{goal}}"), writer="optimizer")
        block = _block(path)
        assert block["parent_sha256"] == content_sha256(_changed("v2: {{goal}}"))
        assert block["ancestors"] == [
            content_sha256(_changed("v2: {{goal}}")),
            content_sha256(WORKFLOW),
        ]

    def test_named_parent_is_used_for_a_renamed_variant(self, library):
        library.add_workflow(WORKFLOW)
        variant = _changed().replace("Project Update", "Project Update Weekly")
        path = library.save(variant, writer="variant_creator", parent="Project Update")
        assert _block(path)["parent_sha256"] == content_sha256(WORKFLOW)

    def test_foreign_user_taints_and_the_taint_is_inherited(self, library):
        library.add_workflow(WORKFLOW)
        library.save(
            _changed("v2: {{goal}}"), writer="optimizer", exposure=Exposure(user_ids=[1, 2])
        )
        path = library.save(
            _changed("v3: {{goal}}"), writer="optimizer", exposure=Exposure(user_ids=[1])
        )
        assert _block(path)["foreign_users"] is True

    def test_owner_runs_do_not_taint(self, library):
        path = library.save(WORKFLOW, writer="creator", exposure=Exposure(user_ids=[1]))
        assert _block(path)["foreign_users"] is False

    def test_unknown_owner_taints_any_user(self, tmp_path):
        library = WorkflowLibrary(tmp_path)
        path = library.save(WORKFLOW, writer="creator", exposure=Exposure(user_ids=[1]))
        assert _block(path)["foreign_users"] is True

    def test_exposure_as_dict(self, library):
        path = library.save(
            WORKFLOW, writer="gym", exposure=Exposure(user_ids=[7], reject=True).to_dict()
        )
        assert _block(path)["foreign_users"] is True

    def test_shown_workflows_taint_a_new_lineage(self, library):
        # Owner-only runs, but the writer was shown a foreign workflow from elsewhere.
        exposure = Exposure(user_ids=[1]).with_shown(
            [{"foreign_users": True, "tainted_by": ["away", "home"]}, None, {"junk": 1}]
        )
        path = library.save(WORKFLOW, writer="optimizer", exposure=exposure)
        block = _block(path)
        assert block["parent_sha256"] is None
        assert block["foreign_users"] is True
        assert block["tainted_by"] == ["home", "away"]

    def test_shown_taint_survives_the_gym_round_trip(self, library):
        exposure = Exposure(user_ids=[1]).with_shown([{"foreign_users": True}])
        restored = Exposure.from_dict(exposure.to_dict())
        assert restored.foreign_users is True
        path = library.save(WORKFLOW, writer="gym", exposure=exposure.to_dict())
        assert _block(path)["foreign_users"] is True

    def test_commons_block_reads_a_workflow_block(self, library):
        library.add_workflow(WORKFLOW)
        assert library.commons_block("Project Update")["sphere"] == "home"
        assert library.commons_block("Missing") is None

    def test_unhashable_workflow_is_saved_without_a_hash(self, library):
        path = library.save(WORKFLOW + "odd: {1: one}\n", writer="human")
        assert _block(path)["content_sha256"] is None

    def test_invalid_yaml_writes_nothing(self, library):
        with pytest.raises(ValueError):
            library.save("- not\n- a mapping\n", writer="human")
        assert list(library.library_path.glob("*.yaml")) == []

    def test_leak_rejected_at_save_writes_nothing(self, library):
        library.add_workflow(WORKFLOW)
        before = {p.name: p.read_text() for p in library.library_path.glob("*.yaml")}
        exposure = Exposure(
            run_texts=["Ask Jane Smith at Acme Corp about the SLA"], user_ids=[1], reject=True
        )
        with pytest.raises(LeakGuardRejected) as caught:
            library.save(
                _changed("Check Acme Corp's SLA with Jane Smith: {{goal}}"),
                writer="optimizer",
                exposure=exposure,
            )
        assert caught.value.record["status"] == "rejected"
        assert {h["text"] for h in caught.value.record["hits"]} >= {"Acme", "Jane"}
        assert {p.name: p.read_text() for p in library.library_path.glob("*.yaml")} == before

    def test_leak_kept_when_the_writer_does_not_reject(self, library):
        exposure = Exposure(goal_texts=["Ask Jane Smith at Acme Corp"], reject=False)
        path = library.save(
            _changed("Check Acme Corp's SLA with Jane Smith: {{goal}}"),
            writer="creator",
            exposure=exposure,
        )
        assert path.exists()


class TestReaders:
    async def test_readers_never_see_the_block(self, library):
        library.add_workflow(WORKFLOW)
        assert "commons" not in library.get_workflow_yaml("Project Update")

    async def test_stamped_workflow_loads_and_lists(self, library):
        library.add_workflow(WORKFLOW)
        assert library.get_workflow("Project Update").first_task_id == "step1"
        (info,) = await library.list_workflows()
        assert info.commons["content_sha256"] == content_sha256(WORKFLOW)

    async def test_legacy_file_without_a_block_still_works(self, library):
        library.ensure_initialized()
        (library.library_path / "project_update.yaml").write_text(WORKFLOW)
        (info,) = await library.list_workflows()
        assert info.name == "Project Update" and info.commons is None
        assert library.get_workflow("Project Update").first_task_id == "step1"
        assert library.get_workflow_yaml("Project Update") == WORKFLOW


class TestOwner:
    async def test_refresh_owner_resolves_once(self, tmp_path):
        calls = []

        async def resolver():
            calls.append(1)
            return 5, "work"

        library = WorkflowLibrary(tmp_path, owner_resolver=resolver)
        assert await library.refresh_owner() == 5
        assert await library.refresh_owner() == 5
        assert library.sphere == "work" and calls == [1]

    async def test_refresh_owner_survives_errors(self, tmp_path):
        async def resolver():
            raise RuntimeError("db down")

        library = WorkflowLibrary(tmp_path, owner_resolver=resolver)
        assert await library.refresh_owner() is None


class TestExportable:
    async def test_foreign_users_are_never_exportable(self, library):
        library.save(WORKFLOW, writer="optimizer", exposure=Exposure(user_ids=[2]))
        (info,) = await library.list_workflows()
        assert commons_exportable(info) is False

    async def test_owner_only_workflow_is_exportable(self, library):
        library.save(WORKFLOW, writer="optimizer", exposure=Exposure(user_ids=[1]))
        (info,) = await library.list_workflows()
        assert commons_exportable(info) is True
