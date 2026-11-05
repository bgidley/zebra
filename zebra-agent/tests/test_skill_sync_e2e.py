"""Skill sync between two devices of one Zebra, end to end over an in-memory relay (#236).

Home (unobserved) and work (observed) are two deployments of the same Zebra: their own
libraries, engines and stores, one private ``InMemoryRelay`` between them. The real
*Skill Share* and *Skill Receive* workflows run with the real actions; only the LLM is
scripted (scans answer clean, the sensitivity check flags job searching).
"""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult
from zebra.definitions.loader import load_definition, validate_definition
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.agent.curator import WorkflowCuratorAction
from zebra_tasks.agent.trust_gate import TrustGateAction
from zebra_tasks.commons.confidentiality import CommonsConfidentialityScanAction
from zebra_tasks.commons.pii_scan import CommonsPiiScanAction
from zebra_tasks.commons.sensitivity import CommonsSensitivityCheckAction
from zebra_tasks.commons.sync_actions import (
    SkillForkResolveAction,
    SkillReceiveAdoptAction,
    SkillReceiveVerifyAction,
    SkillSendAction,
    SkillSharePrepareAction,
    SkillShareRecordAction,
    SkillShareRouteAction,
    SkillSyncRecordAction,
)
from zebra_tasks.llm.action import LLMCallAction
from zebra_tasks.llm.base import LLMProvider, LLMResponse, TokenUsage
from zebra_tasks.llm.client import set_llm_factory

from zebra_agent.commons import keys
from zebra_agent.commons.client import SKILL_KIND, InMemoryCommonsClient, InMemoryRelay
from zebra_agent.commons.identity import make_device_cert
from zebra_agent.commons.sync import SyncService, share_records, share_status
from zebra_agent.genealogy import build_genealogy
from zebra_agent.library import WorkflowLibrary
from zebra_agent.metrics import WorkflowStats
from zebra_agent.provenance import Exposure
from zebra_agent.storage.trust import InMemoryTrustStore, TrustLevel

WORKFLOWS = Path(__file__).parent.parent / "workflows"
OWNER = 1

CHECKLIST = """name: Code Review Checklist
version: 1
description: Review a change against a checklist.
first_task: review
tasks:
  review:
    name: Review
    action: llm_call
    properties:
      prompt: "Review {{goal}} against the team checklist."
"""

JOB_TRACKER = """name: Job Application Tracker
version: 1
description: Track job applications and interview preparation.
first_task: track
tasks:
  track:
    name: Track
    action: llm_call
    properties:
      prompt: "Update my job application list for {{goal}}."
"""

CODENAME = """name: Release Notes
version: 1
description: Draft release notes.
first_task: draft
tasks:
  draft:
    name: Draft
    action: llm_call
    properties:
      prompt: "Draft release notes for the Nightjar launch: {{goal}}"
"""


class ScriptedLLM(LLMProvider):
    """Scans answer clean; the sensitivity check flags anything about jobs."""

    def __init__(self):
        self.prompts: list[str] = []

    async def complete(self, messages, tools=None, temperature=0.7, max_tokens=4096, **kw):
        system, user = str(messages[0].content), str(messages[-1].content)
        self.prompts.append(system[:40])
        if "personal data" in system:
            reply = {"personal_data": False, "findings": []}
        elif "confidential material" in system:
            reply = {"confidential": False, "findings": []}
        elif "would be sensitive" in system:
            sensitive = "job" in user.lower()
            reply = {"sensitive": sensitive, "topics": ["job search"] if sensitive else []}
            reply["reason"] = "job searching" if sensitive else "ordinary work"
        else:
            reply = {}
        return LLMResponse(
            content=json.dumps(reply),
            tool_calls=None,
            finish_reason="end_turn",
            usage=TokenUsage(10, 10),
            model="test/model",
        )

    async def stream(self, *args, **kwargs):
        raise NotImplementedError
        yield ""

    @property
    def name(self) -> str:
        return "scripted"

    @property
    def model(self) -> str:
        return "test/model"

    @property
    def max_context_tokens(self) -> int:
        return 200_000


class Stats:
    """A metrics store with fixed successful-run counts."""

    def __init__(self):
        self.runs: dict[str, int] = {}

    async def get_stats(self, name):
        n = self.runs.get(name, 0)
        return WorkflowStats(workflow_name=name, total_runs=n, successful_runs=n)

    async def get_all_stats(self):
        return [await self.get_stats(n) for n in self.runs]


@dataclass
class Device:
    name: str
    library: WorkflowLibrary
    engine: WorkflowEngine
    sync: SyncService
    stats: Stats
    trust: InMemoryTrustStore

    def save(self, yaml_text: str, **kw):
        return self.library.save(yaml_text, writer="human", **kw)

    async def share_all(self) -> list[str]:
        return await self.sync.after_dream(self.engine, self.library, self.stats)

    async def receive(self) -> list[str]:
        return await self.sync.receive_pending(self.engine, self.library)

    async def pending(self, pid: str):
        return await self.engine.get_pending_tasks(pid)

    async def answer(self, pid: str, task_def: str, output: dict):
        task = next(t for t in await self.pending(pid) if t.task_definition_id == task_def)
        await self.engine.complete_task(task.id, TaskResult.ok(output=output))


def _registry() -> ActionRegistry:
    registry = ActionRegistry()
    registry.register_defaults()
    for name, cls in {
        "llm_call": LLMCallAction,
        "trust_gate": TrustGateAction,
        "commons_pii_scan": CommonsPiiScanAction,
        "commons_confidentiality_scan": CommonsConfidentialityScanAction,
        "commons_sensitivity_check": CommonsSensitivityCheckAction,
        "skill_share_prepare": SkillSharePrepareAction,
        "skill_share_route": SkillShareRouteAction,
        "skill_share_record": SkillShareRecordAction,
        "skill_sync_record": SkillSyncRecordAction,
        "skill_send": SkillSendAction,
        "skill_receive_verify": SkillReceiveVerifyAction,
        "skill_receive_adopt": SkillReceiveAdoptAction,
        "skill_fork_resolve": SkillForkResolveAction,
    }.items():
        registry.register_action(name, cls)
    return registry


@pytest.fixture
def llm():
    model = ScriptedLLM()
    set_llm_factory(lambda m: model)
    return model


@pytest.fixture
def zebra_with(tmp_path, llm):
    """Build the devices of one Zebra, one per sphere ({sphere: observed}), on one relay."""

    def build(spheres: dict[str, bool]):
        builtins = tmp_path / "builtins"
        builtins.mkdir(exist_ok=True)
        for f in ("skill_share.yaml", "skill_receive.yaml"):
            shutil.copy(WORKFLOWS / f, builtins / f)
        zebra_secret = keys.generate_secret_key()
        zebra_pubkey = keys.public_key(zebra_secret)
        relay = InMemoryRelay(private=True)
        secrets = {s: keys.generate_secret_key() for s in spheres}
        certs = [
            make_device_cert(
                zebra_secret,
                keys.public_key(secrets[s]),
                label=f"{s} device",
                sphere=s,
                observed=observed,
            )
            for s, observed in spheres.items()
        ]

        def make(sphere: str, *, direction: str = "both", patterns=()) -> Device:
            stats = Stats()
            library = WorkflowLibrary(
                tmp_path / sphere, stats, owner_user_id=OWNER, sphere=sphere, device=sphere
            )
            library.copy_builtin_workflows(builtins)
            sync = SyncService(
                client=InMemoryCommonsClient(relay),
                device_secret=secrets[sphere],
                zebra_pubkey=zebra_pubkey,
                sphere=sphere,
                observed=spheres[sphere],
                direction=direction,
                certs=list(certs),
                confidential_patterns=list(patterns),
                device_label=f"{sphere} device",
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

        make.relay = relay
        make.secrets = secrets
        return make

    return build


@pytest.fixture
def zebra(zebra_with):
    """Home (unobserved) and work (observed)."""
    return zebra_with({"home": False, "work": True})


def _skill_events(relay: InMemoryRelay) -> list:
    return [e for e in relay.events if e.kind == SKILL_KIND]


def _statuses(device: Device, name: str) -> list[str]:
    return [r["status"] for r in share_records(device.library) if r["name"] == name]


async def _share_to_work_approved(home: Device, work: Device) -> str:
    """Home saves the checklist, runs it twice, and the observed share is approved."""
    home.save(CHECKLIST)
    home.stats.runs["Code Review Checklist"] = 2
    [pid] = await home.share_all()
    await home.answer(
        pid,
        "observed_share_approval",
        {"decision": "approve", "visible_on_managed_device": True},
    )
    return pid


def test_sync_workflows_are_valid():
    for f in ("skill_share.yaml", "skill_receive.yaml"):
        assert validate_definition(load_definition(WORKFLOWS / f)) == []


async def test_new_home_workflow_not_sent_until_approved(zebra):
    home, _work = zebra("home"), zebra("work")
    home.save(CHECKLIST)
    home.stats.runs["Code Review Checklist"] = 1
    assert await home.share_all() == []  # one run is not enough

    home.stats.runs["Code Review Checklist"] = 2
    [pid] = await home.share_all()
    pending = await home.pending(pid)
    assert [t.task_definition_id for t in pending] == ["observed_share_approval"]
    assert _skill_events(zebra.relay) == []
    assert await home.share_all() == []  # never asked twice for the same version

    await home.answer(
        pid,
        "observed_share_approval",
        {"decision": "approve", "visible_on_managed_device": True},
    )

    events = _skill_events(zebra.relay)
    assert len(events) == 1
    assert events[0].tag_values("p") == [keys.public_key(zebra.secrets["work"])]
    block = home.library.commons_block("Code Review Checklist")
    assert block["share_with"] == ["work"]
    assert _statuses(home, "Code Review Checklist")[-2:] == ["approved", "sent"]


async def test_observed_share_without_confirmation_is_declined(zebra):
    home, _work = zebra("home"), zebra("work")
    home.save(CHECKLIST)
    home.stats.runs["Code Review Checklist"] = 2
    [pid] = await home.share_all()
    await home.answer(pid, "observed_share_approval", {"decision": "approve"})

    assert _skill_events(zebra.relay) == []
    assert home.library.commons_block("Code Review Checklist")["share_with"] == []
    assert _statuses(home, "Code Review Checklist")[-1] == "declined"


async def test_freed_owner_still_gets_the_observed_approval(zebra):
    home, _work = zebra("home"), zebra("work")
    await home.trust.set_trust_level(OWNER, "sharing", TrustLevel.AUTONOMOUS, "test", "test")
    # Freed (REQ-TRUST-006) without the cooling-off wait: every trust gate passes now.
    home.trust._freeing[OWNER] = {"freed": True, "initiated_by": "t", "freed_by": "t"}
    assert await home.trust.is_freed(OWNER)
    home.save(CHECKLIST)
    home.stats.runs["Code Review Checklist"] = 2
    [pid] = await home.share_all()

    assert [t.task_definition_id for t in await home.pending(pid)] == ["observed_share_approval"]
    assert _skill_events(zebra.relay) == []


async def test_job_application_workflow_never_proposed_to_work(zebra):
    home, _work = zebra("home"), zebra("work")
    home.save(JOB_TRACKER)
    home.stats.runs["Job Application Tracker"] = 5
    [pid] = await home.share_all()

    process = await home.engine.store.load_process(pid)
    assert process.state == ProcessState.COMPLETE
    assert await home.pending(pid) == []
    assert _skill_events(zebra.relay) == []
    assert _statuses(home, "Job Application Tracker")[-1] == "sensitive"
    assert await home.share_all() == []  # and never asked again


async def test_approved_work_workflow_appears_at_home(zebra):
    home, work = zebra("home"), zebra("work")
    await home.trust.set_trust_level(OWNER, "sharing", TrustLevel.AUTONOMOUS, "test", "test")
    work.save(CHECKLIST)
    work.stats.runs["Code Review Checklist"] = 2
    [pid] = await work.share_all()
    # Work is observed and the workflow is tainted by work: always a human approval.
    await work.answer(pid, "observed_share_approval", {"decision": "approve"})
    assert len(_skill_events(zebra.relay)) == 1

    [rid] = await home.receive()
    assert (await home.engine.store.load_process(rid)).state == ProcessState.COMPLETE
    received = home.library.commons_block("Code Review Checklist")
    sent = work.library.commons_block("Code Review Checklist")
    assert received["content_sha256"] == sent["content_sha256"]
    assert received["sphere"] == "home"
    assert received["tainted_by"] == ["work"]
    assert received["share_with"] == []
    assert await home.receive() == []  # handled once


async def test_received_workflow_waits_for_approval_when_supervised(zebra):
    home, work = zebra("home"), zebra("work")
    work.save(CHECKLIST)
    work.stats.runs["Code Review Checklist"] = 2
    [pid] = await work.share_all()
    await work.answer(pid, "observed_share_approval", {"decision": "approve"})

    [rid] = await home.receive()
    assert [t.task_definition_id for t in await home.pending(rid)] == ["receive_approval"]
    assert home.library.commons_block("Code Review Checklist") is None
    await home.answer(rid, "receive_approval", {"decision": "approve"})
    assert home.library.commons_block("Code Review Checklist") is not None


async def test_codename_blocked_at_work(zebra):
    _home, work = zebra("home"), zebra("work", patterns=[r"\bnightjar\b"])
    work.save(CODENAME)
    work.stats.runs["Release Notes"] = 3
    [pid] = await work.share_all()

    assert await work.pending(pid) == []
    assert _skill_events(zebra.relay) == []
    assert _statuses(work, "Release Notes")[-1] == "blocked"


async def test_receive_only_device_never_sends(zebra):
    _home, work = zebra("home"), zebra("work", direction="receive")
    work.save(CHECKLIST)
    work.stats.runs["Code Review Checklist"] = 9
    assert await work.share_all() == []
    pid = await work.sync.start_share(
        work.engine, work.library, "Code Review Checklist", "home", manual=True
    )
    assert await work.pending(pid) == []
    assert _skill_events(zebra.relay) == []


async def test_edits_on_both_sides_leave_two_versions_and_a_choice(zebra):
    home, work = zebra("home"), zebra("work")
    await home.trust.set_trust_level(OWNER, "sharing", TrustLevel.AUTONOMOUS, "test", "test")
    await work.trust.set_trust_level(OWNER, "sharing", TrustLevel.AUTONOMOUS, "test", "test")
    await _share_to_work_approved(home, work)
    [rid] = await work.receive()
    assert work.library.commons_block("Code Review Checklist") is not None

    home.save(CHECKLIST.replace("team checklist", "home checklist"))
    work.save(CHECKLIST.replace("team checklist", "work checklist"))
    work.stats.runs["Code Review Checklist"] = 2
    [pid] = await work.share_all()
    await work.answer(pid, "observed_share_approval", {"decision": "approve"})

    [rid] = await home.receive()
    pending = await home.pending(rid)
    assert [t.task_definition_id for t in pending] == ["fork_choice"]
    mine = home.library.commons_block("Code Review Checklist")
    theirs = home.library.commons_block("Code Review Checklist (from work)")
    assert mine["fork_of"] == theirs["content_sha256"]
    assert theirs["fork_of"] == mine["content_sha256"]
    assert "home checklist" in home.library.get_workflow_yaml("Code Review Checklist")

    # Neither fork is retired by the curator while the choice waits.
    task = type("T", (), {"properties": {}, "id": "t"})()
    decisions = WorkflowCuratorAction()._rule_decisions(
        task, home.library.list_workflow_files(), {}
    )
    assert not [d for d in decisions if "Code Review Checklist" in d["workflow"]]

    genealogy = build_genealogy(home.library, "Code Review Checklist")
    assert (
        genealogy.forks and genealogy.forks[0]["fork_name"] == "Code Review Checklist (from work)"
    )

    await home.answer(rid, "fork_choice", {"keep": "theirs"})
    assert "work checklist" in home.library.get_workflow_yaml("Code Review Checklist")
    assert home.library.commons_block("Code Review Checklist")["fork_of"] is None
    assert not home.library._files_named("Code Review Checklist (from work)")


async def test_share_back_shows_the_diff_against_the_copy_received_from_there(zebra):
    """A workflow that came from work, edited at home, is shown as a change to work's copy."""
    home, work = zebra("home"), zebra("work")
    await home.trust.set_trust_level(OWNER, "sharing", TrustLevel.AUTONOMOUS, "test", "test")
    work.save(CHECKLIST)
    work.stats.runs["Code Review Checklist"] = 2
    [pid] = await work.share_all()
    await work.answer(pid, "observed_share_approval", {"decision": "approve"})
    [rid] = await home.receive()
    assert home.library.commons_block("Code Review Checklist") is not None

    home.save(CHECKLIST.replace("team checklist", "home checklist"))
    home.stats.runs["Code Review Checklist"] = 2
    [pid] = await home.share_all()
    assert [t.task_definition_id for t in await home.pending(pid)] == ["observed_share_approval"]
    diff = (await home.engine.store.load_process(pid)).properties["share"]["diff"]
    assert "no copy in work" not in diff
    assert "-" in diff and "+" in diff
    assert "home checklist" in diff and "team checklist" in diff


async def test_fast_forward_replaces_and_stale_is_ignored(zebra):
    home, work = zebra("home"), zebra("work")
    await home.trust.set_trust_level(OWNER, "sharing", TrustLevel.AUTONOMOUS, "test", "test")
    await work.trust.set_trust_level(OWNER, "sharing", TrustLevel.AUTONOMOUS, "test", "test")
    await _share_to_work_approved(home, work)
    await work.receive()
    first = work.library.commons_block("Code Review Checklist")["content_sha256"]

    home.save(CHECKLIST.replace("team checklist", "better checklist"))
    [pid] = await home.share_all()  # a new version is a new decision
    await home.answer(
        pid, "observed_share_approval", {"decision": "approve", "visible_on_managed_device": True}
    )
    await work.receive()
    block = work.library.commons_block("Code Review Checklist")
    assert block["content_sha256"] != first
    assert first in block["ancestors"]
    assert len(work.library._files_named("Code Review Checklist")) == 1


async def test_workflow_learnt_from_another_users_runs_is_never_proposed(zebra):
    home, _work = zebra("home"), zebra("work")
    home.library.save(
        CHECKLIST,
        writer="creator",
        exposure=Exposure(user_ids=[OWNER, 2]),
    )
    assert home.library.commons_block("Code Review Checklist")["foreign_users"] is True
    home.stats.runs["Code Review Checklist"] = 10
    assert await home.share_all() == []
    assert _skill_events(zebra.relay) == []


async def test_genealogy_shows_share_status(zebra):
    home, work = zebra("home"), zebra("work")
    await _share_to_work_approved(home, work)
    genealogy = build_genealogy(home.library, "Code Review Checklist")
    assert [(s["sphere"], s["status"]) for s in genealogy.share_status] == [("work", "sent")]
    block = home.library.commons_block("Code Review Checklist")
    status = share_status(home.library, "Code Review Checklist", block["content_sha256"], block)
    assert status[0]["label"] == "shared"


async def test_earned_autonomy_skips_approval_only_for_unobserved_untainted(zebra_with):
    make = zebra_with({"home": False, "studio": False})
    home, studio = make("home"), make("studio")
    home.save(CHECKLIST)
    home.stats.runs["Code Review Checklist"] = 2

    # SUPERVISED sharing: the plain "Share X with studio?" task, not the observed one
    [pid] = await home.share_all()
    assert [t.task_definition_id for t in await home.pending(pid)] == ["share_approval"]
    await home.answer(pid, "share_approval", {"decision": "decline"})
    assert make.relay.events == []

    # AUTONOMOUS sharing skips the task for a new, untainted-by-observed version
    await home.trust.set_trust_level(OWNER, "sharing", TrustLevel.AUTONOMOUS, "test", "test")
    home.save(CHECKLIST.replace("team checklist", "studio checklist"))
    [pid] = await home.share_all()
    assert await home.pending(pid) == []
    assert len(_skill_events(make.relay)) == 1
    [rid] = await studio.receive()
    # The receiver's own sharing level governs adoption: SUPERVISED there, so it asks.
    assert [t.task_definition_id for t in await studio.pending(rid)] == ["receive_approval"]


# --- leak-guard taint: kept / error results block a share (O2) ------------------------

LEAKY = CHECKLIST.replace(
    "Review {{goal}} against the team checklist.",
    "Check Acme Corp's SLA with Jane Smith, then review {{goal}} against the checklist.",
)
LEAKY_EDITED = LEAKY.replace("then review", "and then carefully review")


def _leak_exposure() -> Exposure:
    return Exposure(goal_texts=["Ask Jane Smith at Acme Corp"], reject=False)


def _last_saved(device: Device) -> dict:
    return [r for r in device.library.journal.read() if r["event"] == "saved"][-1]


async def _assert_blocked(home: Device, relay: InMemoryRelay) -> None:
    home.stats.runs["Code Review Checklist"] = 2
    await home.share_all()
    assert _skill_events(relay) == []
    statuses = _statuses(home, "Code Review Checklist")
    assert statuses[-1] == "blocked"
    assert "approved" not in statuses and "sent" not in statuses
    assert home.library.commons_block("Code Review Checklist")["share_with"] == []
    assert await home.share_all() == []  # never proposed again at this hash


async def test_leak_kept_version_is_never_sent(zebra):
    home, _work = zebra("home"), zebra("work")
    home.library.save(LEAKY, writer="creator", exposure=_leak_exposure())
    assert _last_saved(home)["leak_guard"]["status"] == "kept"
    await _assert_blocked(home, zebra.relay)


async def test_writer_leak_record_does_not_hide_a_kept_save_check(zebra):
    home, _work = zebra("home"), zebra("work")
    home.library.save(
        LEAKY,
        writer="creator",
        exposure=_leak_exposure(),
        leak={"status": "generalised", "hits": []},
    )
    record = _last_saved(home)["leak_guard"]
    assert record["status"] == "generalised"
    assert record["save_check"] == "kept"
    await _assert_blocked(home, zebra.relay)


async def test_edit_of_a_kept_version_inherits_the_taint(zebra):
    home, _work = zebra("home"), zebra("work")
    home.library.save(LEAKY, writer="creator", exposure=_leak_exposure())
    kept_hash = home.library.commons_block("Code Review Checklist")["content_sha256"]
    home.save(LEAKY_EDITED)  # a human edit: the literal is in the parent, so no new hit
    block = home.library.commons_block("Code Review Checklist")
    assert block["content_sha256"] != kept_hash
    assert kept_hash in (block.get("ancestors") or []) + [block.get("parent_sha256")]
    assert (_last_saved(home)["leak_guard"] or {}).get("status") != "kept"
    await _assert_blocked(home, zebra.relay)


async def test_leak_check_error_fails_closed(zebra, monkeypatch):
    from zebra_tasks.agent import leak_guard

    def broken(self, yaml_text):
        raise RuntimeError("guard crashed")

    home, _work = zebra("home"), zebra("work")
    monkeypatch.setattr(leak_guard.LeakGuard, "check", broken)
    home.library.save(CHECKLIST, writer="creator", exposure=_leak_exposure())
    record = _last_saved(home)["leak_guard"]
    assert record["status"] == "error"
    assert record["check_failed"] is True
    await _assert_blocked(home, zebra.relay)


async def test_writer_error_status_fails_closed(zebra):
    home, _work = zebra("home"), zebra("work")
    home.library.save(CHECKLIST, writer="creator", leak={"status": "error", "hits": []})
    await _assert_blocked(home, zebra.relay)


async def test_clean_save_is_not_tainted(zebra):
    from zebra_agent.commons.sync import leak_kept

    home, _work = zebra("home"), zebra("work")
    home.library.save(CHECKLIST, writer="creator", leak={"status": "generalised", "hits": []})
    block = home.library.commons_block("Code Review Checklist")
    assert leak_kept(home.library, block["content_sha256"], block) is False


async def test_send_refuses_a_tainted_version_even_when_approved(zebra):
    from zebra_agent.commons.skill import SkillRefused, skill_payload
    from zebra_agent.commons.sync import bytes_sha256

    home, _work = zebra("home"), zebra("work")
    path = home.library.save(LEAKY, writer="creator", exposure=_leak_exposure())
    content_hash = home.library.commons_block("Code Review Checklist")["content_sha256"]
    assert home.library.approve_share("Code Review Checklist", "work", content_hash)
    with pytest.raises(SkillRefused, match="leak guard"):
        await home.sync.send(
            home.library,
            "Code Review Checklist",
            spheres=["work"],
            expected_sha256=content_hash,
            scanned_bytes_sha256=bytes_sha256(skill_payload(path.read_text())),
        )
    assert _skill_events(zebra.relay) == []


async def test_version_with_no_journal_record_is_tainted(zebra):
    """A version saved before the lineage journal (or with the journal lost) fails closed."""
    from zebra_agent.commons.sync import leak_kept

    home, _work = zebra("home"), zebra("work")
    home.save(CHECKLIST)
    block = home.library.commons_block("Code Review Checklist")
    assert leak_kept(home.library, block["content_sha256"], block) is False
    home.library.journal.path.unlink()  # no `saved` record of who wrote it
    assert leak_kept(home.library, block["content_sha256"], block) is True
    await _assert_blocked(home, zebra.relay)


async def test_ancestor_with_no_journal_record_taints_its_descendants(zebra):
    from zebra_agent.commons.sync import leak_kept

    home, _work = zebra("home"), zebra("work")
    home.save(CHECKLIST)
    first = home.library.commons_block("Code Review Checklist")["content_sha256"]
    home.save(CHECKLIST.replace("team checklist", "better checklist"))
    block = home.library.commons_block("Code Review Checklist")
    assert leak_kept(home.library, block["content_sha256"], block) is False
    # Drop the first version's record, as if it was saved before the journal existed.
    path = home.library.journal.path
    kept = [
        line
        for line in path.read_text().splitlines()
        if not (json.loads(line).get("content_sha256") == first and '"saved"' in line)
    ]
    path.write_text("\n".join(kept) + "\n")
    assert leak_kept(home.library, block["content_sha256"], block) is True
    await _assert_blocked(home, zebra.relay)


async def test_unmodified_builtin_needs_no_journal_record(zebra):
    from zebra_agent.commons.sync import leak_kept

    home = zebra("home")
    block = home.library.commons_block("Skill Share")
    assert block["content_sha256"] in home.library.builtin_hashes()
    assert leak_kept(home.library, block["content_sha256"], block) is False


# --- the run-count trigger: a goal run reaching MIN_RUNS_TO_SHARE proposes a share ----

GOAL_RUN = """name: Goal Run
version: 1
description: Record one run of a goal workflow, as the Agent Main Loop does.
first_task: assess_and_record
tasks:
  assess_and_record:
    name: Assess and Record
    action: assess_and_record
    properties:
      run_id: "{{run_id}}"
      workflow_name: "{{workflow_name}}"
      goal: "Review my change"
      success: "{{success}}"
"""


async def _goal_run(device: Device, metrics, n: int, *, success: bool = True) -> None:
    from zebra.definitions.loader import load_definition_from_yaml

    process = await device.engine.create_process(
        load_definition_from_yaml(GOAL_RUN),
        properties={
            "run_id": f"run-{n}",
            "workflow_name": "Code Review Checklist",
            "success": success,
            "__user_id__": OWNER,
        },
    )
    await device.engine.start_process(process.id)
    finished = await device.engine.store.load_process(process.id)
    assert finished.state == ProcessState.COMPLETE


async def _share_processes(device: Device) -> list:
    processes = []
    for state in (ProcessState.RUNNING, ProcessState.COMPLETE, ProcessState.FAILED):
        processes += await device.engine.store.get_processes_by_state(state)
    return [p for p in processes if p.properties.get("target_sphere")]


async def test_second_successful_goal_run_proposes_the_share(zebra):
    from zebra_tasks.agent.assess_and_record import AssessAndRecordAction

    from zebra_agent.storage.metrics import InMemoryMetricsStore

    home, _work = zebra("home"), zebra("work")
    metrics = InMemoryMetricsStore()
    home.engine.actions.register_action("assess_and_record", AssessAndRecordAction)
    home.engine.extras["__metrics_store__"] = metrics
    home.save(CHECKLIST)

    await _goal_run(home, metrics, 1)
    await _goal_run(home, metrics, 2, success=False)  # a failed run proposes nothing
    assert await _share_processes(home) == []
    assert _statuses(home, "Code Review Checklist") == []

    await _goal_run(home, metrics, 3)  # the second success
    [share] = await _share_processes(home)
    assert share.properties["trigger"] == "runs"
    pending = await home.pending(share.id)
    assert [t.task_definition_id for t in pending] == ["observed_share_approval"]
    assert _statuses(home, "Code Review Checklist") == ["proposed"]
    assert _skill_events(zebra.relay) == []

    await _goal_run(home, metrics, 4)  # never asked twice for the same version
    assert len(await _share_processes(home)) == 1


async def test_goal_run_without_a_sync_service_proposes_nothing(zebra):
    from zebra_tasks.agent.assess_and_record import AssessAndRecordAction

    from zebra_agent.storage.metrics import InMemoryMetricsStore

    home, _work = zebra("home"), zebra("work")
    metrics = InMemoryMetricsStore()
    home.engine.actions.register_action("assess_and_record", AssessAndRecordAction)
    home.engine.extras["__metrics_store__"] = metrics
    del home.engine.extras["__commons_sync__"]
    home.save(CHECKLIST)
    for n in range(3):
        await _goal_run(home, metrics, n)
    assert await _share_processes(home) == []


def test_sync_direction_from_the_environment(monkeypatch, zebra):
    from zebra_agent.commons.sync import configured_direction

    assert configured_direction({}) == "both"
    assert configured_direction({"ZEBRA_SYNC_DIRECTION": " Receive "}) == "receive"
    assert configured_direction({"ZEBRA_SYNC_DIRECTION": "sideways"}) == "off"  # fail closed

    monkeypatch.setenv("ZEBRA_SYNC_DIRECTION", "off")
    sync = SyncService(
        client=InMemoryCommonsClient(zebra.relay),
        device_secret=zebra.secrets["work"],
        zebra_pubkey="0" * 64,
        sphere="work",
    )
    assert sync.direction == "off"
    assert not sync.can_send and not sync.can_receive


# --- proposal records: skips and failures never look like a waiting proposal ---------


async def test_skipped_proposal_is_not_waiting_for_approval(zebra):
    _home, work = zebra("home"), zebra("work", direction="receive")
    work.save(CHECKLIST)
    pid = await work.sync.start_share(
        work.engine, work.library, "Code Review Checklist", "home", manual=True
    )
    assert await work.pending(pid) == []
    assert _statuses(work, "Code Review Checklist") == ["skipped"]
    block = work.library.commons_block("Code Review Checklist")
    [status] = share_status(work.library, "Code Review Checklist", block["content_sha256"], block)
    assert status["label"] == "not proposed"

    # A skip is not a decision: once the device may send, Zebra can ask.
    work.sync.direction = "both"
    work.stats.runs["Code Review Checklist"] = 2
    [pid] = await work.share_all()
    assert [t.task_definition_id for t in await work.pending(pid)] == ["observed_share_approval"]
    assert _statuses(work, "Code Review Checklist")[-1] == "proposed"


async def test_failed_share_process_is_recorded_and_asked_again(zebra, monkeypatch):
    home, _work = zebra("home"), zebra("work")
    home.save(CHECKLIST)
    home.stats.runs["Code Review Checklist"] = 2

    async def crash(self, task, context):
        raise RuntimeError("scanner crashed")

    monkeypatch.setattr(CommonsPiiScanAction, "run", crash)
    [pid] = await home.share_all()
    assert (await home.engine.store.load_process(pid)).state == ProcessState.FAILED
    assert _statuses(home, "Code Review Checklist")[-1] == "failed"
    block = home.library.commons_block("Code Review Checklist")
    [status] = share_status(home.library, "Code Review Checklist", block["content_sha256"], block)
    assert status["label"] == "share failed"
    assert _skill_events(zebra.relay) == []

    monkeypatch.undo()
    [pid] = await home.share_all()
    assert [t.task_definition_id for t in await home.pending(pid)] == ["observed_share_approval"]


# --- O3: approvals bind to one version; autonomy never covers observed taint ---------


async def test_approval_is_void_once_the_content_changes(zebra):
    home, _work = zebra("home"), zebra("work")
    home.save(CHECKLIST)
    home.stats.runs["Code Review Checklist"] = 2
    [pid] = await home.share_all()
    proposed = home.library.commons_block("Code Review Checklist")["content_sha256"]

    home.save(CHECKLIST.replace("team checklist", "edited checklist"))  # edit while it waits
    await home.answer(
        pid,
        "observed_share_approval",
        {"decision": "approve", "visible_on_managed_device": True},
    )

    assert _skill_events(zebra.relay) == []
    records = [r for r in share_records(home.library) if r["content_sha256"] == proposed]
    assert [r["status"] for r in records] == ["proposed", "declined"]
    assert "changed" in records[-1]["reason"]
    block = home.library.commons_block("Code Review Checklist")
    assert block["content_sha256"] != proposed
    assert block["share_with"] == []


async def test_autonomy_on_the_sender_never_skips_observed_taint(zebra_with):
    """Work → home by sync, then home (AUTONOMOUS) shares it on to an unobserved studio."""
    make = zebra_with({"home": False, "work": True, "studio": False})
    home, work, _studio = make("home"), make("work"), make("studio")
    await home.trust.set_trust_level(OWNER, "sharing", TrustLevel.AUTONOMOUS, "test", "test")

    work.save(CHECKLIST)
    work.stats.runs["Code Review Checklist"] = 2
    for pid in await work.share_all():  # to home (and studio): both from observed work
        share = (await work.engine.store.load_process(pid)).properties
        if share["target_sphere"] == "home":
            await work.answer(pid, "observed_share_approval", {"decision": "approve"})
    [rid] = await home.receive()  # AUTONOMOUS home adopts without asking
    assert (await home.engine.store.load_process(rid)).state == ProcessState.COMPLETE
    block = home.library.commons_block("Code Review Checklist")
    assert block["tainted_by"] == ["work"]
    sent_before = len(_skill_events(make.relay))

    home.stats.runs["Code Review Checklist"] = 2
    [pid] = await home.share_all()  # to studio only: work already decided (received)
    assert (await home.engine.store.load_process(pid)).properties["target_sphere"] == "studio"
    assert [t.task_definition_id for t in await home.pending(pid)] == ["observed_share_approval"]
    assert len(_skill_events(make.relay)) == sent_before
