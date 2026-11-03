"""Tests for the lineage journal and the private genealogy model (#238)."""

import json
import os
import shutil

import pytest

from zebra_agent.genealogy import (
    LineageJournal,
    build_genealogy,
    merge_leak,
    normalize_reason,
    scrub_leak,
    writer_label,
)
from zebra_agent.library import BUILTIN_WORKFLOWS_DIR, LeakGuardRejected, WorkflowLibrary
from zebra_agent.provenance import Exposure, content_sha256, read_commons

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


def _changed(prompt: str) -> str:
    return WORKFLOW.replace("Update the plan: {{goal}}", prompt)


V2 = _changed("v2: {{goal}}")
V3 = _changed("v3: {{goal}}")


@pytest.fixture
def library(tmp_path):
    return WorkflowLibrary(
        tmp_path / "workflows", owner_user_id=1, sphere="home", device="Ben's laptop"
    )


def _journal(library) -> list[dict]:
    return LineageJournal(library.library_path).read()


# ---------------------------------------------------------------------------
# The journal (O1)
# ---------------------------------------------------------------------------


class TestJournal:
    def test_every_writer_is_journaled_with_time_sphere_and_device(self, library):
        library.add_workflow(WORKFLOW)
        library.save(V2, writer="optimizer", reason={"text": "three failed runs"})
        library.save(V3, writer="gym", reason="scored no worse")
        library.save(
            _changed("v4: {{goal}}").replace("Project Update", "Weekly Update"),
            writer="variant_creator",
            parent="Project Update",
            reason={"text": "I needed a weekly version", "kind": "voice", "source": "selector"},
        )
        library.save(
            _changed("new").replace("Project Update", "Fresh"), writer="creator", reason=None
        )

        records = _journal(library)
        assert [r["writer"] for r in records] == [
            "human",
            "optimizer",
            "gym",
            "variant_creator",
            "creator",
        ]
        assert all(r["event"] == "saved" and r["v"] == 1 for r in records)
        assert all(r["sphere"] == "home" and r["device"] == "Ben's laptop" for r in records)
        assert all(r["at"].endswith("+00:00") for r in records)
        assert [r["at"] for r in records] == sorted(r["at"] for r in records)
        human, optimizer, gym, variant, creator = records
        assert human["reason"] is None and human["parent_sha256"] is None
        assert optimizer["reason"] == {"text": "three failed runs", "kind": "reasoning"}
        assert optimizer["content_sha256"] == content_sha256(V2)
        assert optimizer["parent_sha256"] == content_sha256(WORKFLOW)
        assert gym["reason"]["text"] == "scored no worse"
        assert variant["reason"]["kind"] == "voice"
        assert variant["parent_name"] == "Project Update"
        assert creator["reason"] is None

    def test_the_journal_does_not_change_the_block_or_hash(self, library, tmp_path):
        plain = WorkflowLibrary(tmp_path / "plain", owner_user_id=1, sphere="home")
        a = library.save(WORKFLOW, writer="human", reason="why", leak={"status": "kept"})
        b = plain.save(WORKFLOW, writer="human")
        assert a.read_text() == b.read_text()
        assert "why" not in a.read_text()
        assert read_commons(a.read_text())["content_sha256"] == content_sha256(WORKFLOW)

    def test_a_save_time_rejection_is_journaled_without_a_file_or_hit_text(self, library):
        library.add_workflow(WORKFLOW)
        exposure = Exposure(
            run_texts=["Ask Jane Smith at Acme Corp about the SLA"], user_ids=[1], reject=True
        )
        with pytest.raises(LeakGuardRejected):
            library.save(
                _changed("Check Acme Corp's SLA with Jane Smith: {{goal}}"),
                writer="optimizer",
                exposure=exposure,
                reason="SLA questions keep failing",
            )
        rejected = _journal(library)[-1]
        assert rejected["event"] == "rejected" and rejected["file"] is None
        assert rejected["reason"]["text"] == "SLA questions keep failing"
        assert rejected["leak_guard"]["status"] == "rejected"
        assert {h["kind"] for h in rejected["leak_guard"]["hits"]} == {"name"}
        text = library.journal.path.read_text()
        assert "Jane" not in text and "Acme" not in text
        assert len(list(library.library_path.glob("*.yaml"))) == 1

    def test_kept_hits_are_recorded_without_text(self, library):
        exposure = Exposure(goal_texts=["Ask Jane Smith at Acme Corp"], reject=False)
        library.save(
            _changed("Check Acme Corp's SLA with Jane Smith: {{goal}}"),
            writer="creator",
            exposure=exposure,
        )
        record = _journal(library)[-1]
        assert record["leak_guard"]["status"] == "kept"
        assert record["leak_guard"]["hits"] and "Jane" not in library.journal.path.read_text()

    def test_a_journal_failure_does_not_fail_the_save(self, library):
        library.ensure_initialized()
        (library.library_path / ".lineage").write_text("not a directory")
        path = library.save(WORKFLOW, writer="human")
        assert path.exists()
        assert _journal(library) == []

    def test_bad_lines_are_skipped(self, library):
        library.add_workflow(WORKFLOW)
        with library.journal.path.open("a") as f:
            f.write("{not json\n[1]\n")
        library.save(V2, writer="optimizer")
        assert [r["writer"] for r in _journal(library)] == ["human", "optimizer"]

    def test_helpers(self):
        assert normalize_reason("  ") is None
        assert normalize_reason({"text": "a  b", "kind": "odd"}) == {
            "text": "a b",
            "kind": "reasoning",
        }
        assert scrub_leak({"status": "rejected", "error": "boom Jane"}) == {
            "status": "rejected",
            "hits": [],
            "check_failed": True,
        }
        merged = merge_leak(
            {"status": "generalised", "hits": [{"kind": "name", "text": "x", "where": "a"}]},
            {"status": "kept", "hits": [{"kind": "email", "text": "y", "where": "b"}]},
        )
        assert [h["kind"] for h in merged["hits"]] == ["name", "email"]
        assert merged["save_check"] == "kept"
        assert writer_label("gym") == "optimizer" and writer_label(None) == "unknown"


# ---------------------------------------------------------------------------
# The genealogy (O2, O3)
# ---------------------------------------------------------------------------


class TestGenealogy:
    def test_two_optimizations_give_a_chain_of_three(self, library):
        library.add_workflow(WORKFLOW)
        library.save(V2, writer="optimizer", reason="three failed runs at work")
        library.save(V3, writer="optimizer", reason="answers were too long")

        g = build_genealogy(library, "Project Update")
        h1, h2, h3 = (content_sha256(y) for y in (WORKFLOW, V2, V3))
        assert [v.key for v in g.versions] == [h3, h2, h1]
        assert g.edges == sorted([(h1, h2), (h2, h3)])
        assert g.current == h3 and g.version(h3).current
        v3, v2, v1 = g.versions
        assert [v.layer for v in (v1, v2, v3)] == [0, 1, 2]
        assert v1.parents == [] and v1.diff is None and v1.writer_label == "human"
        assert v2.writer_label == "optimizer" and v2.reason["text"] == "three failed runs at work"
        assert '-      prompt: "Update the plan' in v2.diff and '+      prompt: "v2' in v2.diff
        assert v3.reason["text"] == "answers were too long"
        assert v3.sphere == "home" and v3.device == "Ben's laptop"
        assert v3.date_source == "journal" and v3.tainted_by == ["home"]

    def test_a_variant_branches_off_under_its_own_name(self, library):
        library.add_workflow(WORKFLOW)
        weekly = _changed("weekly: {{goal}}").replace("Project Update", "Weekly Update")
        library.save(weekly, writer="variant_creator", parent="Project Update")
        library.save(V2, writer="optimizer")

        h2, hw = content_sha256(V2), content_sha256(weekly)
        for name in ("Project Update", "Weekly Update"):
            g = build_genealogy(library, name)
            root = g.version(content_sha256(WORKFLOW))
            assert sorted(root.children) == sorted([h2, hw])
        g = build_genealogy(library, "Weekly Update")
        assert g.current == hw and g.version(hw).writer_label == "variant"
        assert g.version(hw).names == ["Weekly Update"]

    def test_unrelated_workflows_are_left_out(self, library):
        library.add_workflow(WORKFLOW)
        library.add_workflow(_changed("other").replace("Project Update", "Other"))
        g = build_genealogy(library, "Project Update")
        assert len(g.versions) == 1

    def test_unknown_workflow(self, library):
        assert build_genealogy(library, "Missing") is None

    def test_legacy_file_is_unknown_and_dated_by_the_file(self, library):
        library.ensure_initialized()
        (library.library_path / "project_update.yaml").write_text(WORKFLOW)
        library.save(V2, writer="optimizer")
        g = build_genealogy(library, "Project Update")
        old = g.version(content_sha256(WORKFLOW))
        assert old.legacy and old.writer_label == "unknown" and old.date_source == "file"
        assert old.reason is None
        assert g.version(content_sha256(V2)).parents == [old.key]

    def test_an_unmodified_builtin_is_labelled_built_in(self, library):
        library.ensure_initialized()
        source = next(BUILTIN_WORKFLOWS_DIR.glob("*.yaml"))
        shutil.copy(source, library.library_path / source.name)
        name = next(w.name for w in library.list_workflow_files())
        g = build_genealogy(library, name)
        (version,) = g.versions
        assert version.writer_label == "built-in" and version.legacy

    def test_retired_versions_are_kept_with_their_reason(self, library):
        library.add_workflow(WORKFLOW)
        first = next(library.library_path.glob("*.yaml"))
        os.utime(first, (1_000_000, 1_000_000))
        library.save(V2, writer="optimizer")
        library.retire("Project Update", "superseded", path=first)
        g = build_genealogy(library, "Project Update")
        old = g.version(content_sha256(WORKFLOW))
        assert old.retired["reason"] == "superseded" and not old.active
        assert old.files == ["retired/project_update.yaml"]
        assert g.version(content_sha256(V2)).diff

    def test_retired_only_workflow_still_has_a_genealogy(self, library):
        library.add_workflow(WORKFLOW)
        library.retire("Project Update", "unused")
        g = build_genealogy(library, "Project Update")
        assert g.current == content_sha256(WORKFLOW) and g.versions[0].retired

    def test_ancestors_without_a_file_are_hash_only(self, library):
        library.add_workflow(WORKFLOW)
        library.save(V2, writer="optimizer")
        library.save(V3, writer="optimizer")
        for path in library.library_path.glob("*.yaml"):
            if read_commons(path.read_text())["content_sha256"] != content_sha256(V3):
                path.unlink()
        g = build_genealogy(library, "Project Update")
        h1, h2, h3 = (content_sha256(y) for y in (WORKFLOW, V2, V3))
        assert [v.key for v in g.versions][0] == h3
        assert {h1, h2} == {v.key for v in g.versions if v.hash_only}
        assert (h1, h2) in g.edges and (h2, h3) in g.edges
        assert g.version(h3).diff is None  # the parent's file is gone
        # The journal still knows who made a version whose file is gone.
        assert g.version(h2).writer_label == "optimizer"

    def test_a_revert_cycle_is_laid_out(self, library):
        library.add_workflow(WORKFLOW)
        library.save(V2, writer="optimizer")
        library.save(WORKFLOW, writer="human")  # back to the original content
        g = build_genealogy(library, "Project Update")
        h1, h2 = content_sha256(WORKFLOW), content_sha256(V2)
        assert {(h1, h2), (h2, h1)} <= set(g.edges)
        assert sorted(v.layer for v in g.versions) == [0, 1]

    def test_refused_saves_are_listed(self, library):
        library.add_workflow(WORKFLOW)
        with pytest.raises(LeakGuardRejected):
            library.save(
                _changed("Check Acme Corp's SLA with Jane Smith: {{goal}}"),
                writer="optimizer",
                exposure=Exposure(run_texts=["Jane Smith at Acme Corp"], reject=True),
            )
        g = build_genealogy(library, "Project Update")
        (refused,) = g.rejected
        assert refused["writer_label"] == "optimizer"
        assert refused["leak_guard"]["status"] == "rejected"
        assert "Jane" not in json.dumps(refused, default=str)

    def test_share_status_and_forks_are_empty_until_sync(self, library):
        library.add_workflow(WORKFLOW)
        g = build_genealogy(library, "Project Update")
        assert g.share_status == [] and g.forks == []
