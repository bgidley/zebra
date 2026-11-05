"""The judged *Commons Import* pipeline end to end (Commons S3, #230).

Runs the real ``commons_import.yaml`` on a real engine with every registered action.
Only the LLM is faked: the personal-data scan finds nothing, the ethics gate approves,
the imported workflow answers "Canberra" and the gym's judge scores an answer 1 when it
mentions Canberra. There is no trust store, so the ``sharing`` gate fails closed to the
owner's approval task, as at SUPERVISED.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from importlib.metadata import entry_points
from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.commons.supervised import (
    APPROVAL_TASK,
    SUPERVISED_LAUNCH_KEY,
    WRAPPER_NAME_PREFIX,
)
from zebra_tasks.llm.base import LLMResponse, TokenUsage
from zebra_tasks.llm.client import set_llm_factory

from zebra_agent.commons import keys
from zebra_agent.commons.export import export_workflow
from zebra_agent.commons.identity import make_device_cert
from zebra_agent.library import WorkflowLibrary
from zebra_agent.provenance import read_commons
from zebra_agent.scheduler.loop import SchedulerLoop
from zebra_agent.scheduler.registry import RoutineRegistry
from zebra_agent.scheduler.routine import Routine, RoutineRun
from zebra_agent.scheduler.store import InMemoryRoutineRunStore
from zebra_agent.scheduler.testing import FakeClock

BUILTIN = Path(__file__).resolve().parents[1] / "workflows"
LOCAL_NAME = "Capital Facts (from Pub Zebra)"


def _workflow(prompt: str = "Answer: {{goal}}", extra: str = "") -> str:
    return f"""name: "Capital Facts"
description: "Answer questions about capital cities"
tags: [facts]
version: 1
first_task: answer
tasks:
  answer:
    name: "Answer"
    action: llm_call
    properties:
      prompt: "{prompt}"
      output_key: answer
{extra}
routings: []
"""


GOLDEN = [
    {
        "goal": "What is the capital of Australia?",
        "expected": "Canberra",
        "criteria": ["Names Canberra"],
    }
]


class _FakeLLM:
    """One fake for every LLM call in the pipeline, told apart by the system prompt."""

    model = "fake"

    def __init__(self, answer: str = "Canberra"):
        self.answer = answer
        self.calls: list[str] = []

    async def complete(self, messages, **kwargs) -> LLMResponse:
        system = messages[0].content if messages and messages[0].role == "system" else ""
        user = messages[-1].content
        if "Find personal data" in system:
            kind, content = "pii", '{"personal_data": false, "findings": []}'
        elif "grade the output of an AI workflow" in system:
            score = 1 if "Canberra" in user.split("## Workflow output", 1)[1] else 0
            kind = "judge"
            content = json.dumps(
                {"criteria": [{"criterion": 1, "score": score}], "reasoning": "ok"}
            )
        elif "Kant" in system or "ethic" in system.lower():
            kind = "ethics"
            content = json.dumps(
                {
                    "approved": True,
                    "overall_reasoning": "A harmless facts workflow.",
                    "concerns": [],
                }
            )
        else:
            kind, content = "workflow", self.answer
        self.calls.append(kind)
        return LLMResponse(
            content=content,
            tool_calls=None,
            finish_reason="stop",
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            model=self.model,
        )


class _Commons:
    def __init__(self, stopped: str | None = None):
        self.stopped = stopped

    async def stop_reason(self) -> str | None:
        return self.stopped

    async def held_events(self) -> list:
        return []


@pytest.fixture
def llm() -> _FakeLLM:
    fake = _FakeLLM()
    set_llm_factory(lambda model: fake)
    return fake


@pytest.fixture
def publisher_keys():
    zebra_secret = keys.generate_secret_key()
    device_secret = keys.generate_secret_key()
    cert = make_device_cert(
        zebra_secret, keys.public_key(device_secret), label="Pub", sphere="home", observed=False
    )
    return keys.public_key(zebra_secret), device_secret, cert


async def _export(
    tmp_path: Path, publisher_keys, yaml_text: str, golden=GOLDEN, name: str = "Capital Facts"
) -> str:
    zebra_pub, device_secret, cert = publisher_keys
    pub = WorkflowLibrary(tmp_path / f"pub-{len(list(tmp_path.iterdir()))}", owner_user_id=1)
    pub.add_workflow(yaml_text)
    golden_dir = pub.library_path.parent / "golden-pub"
    golden_dir.mkdir(exist_ok=True)
    for i, task in enumerate(golden or []):
        data = {"id": f"g{i}", "workflow": name, **task}
        (golden_dir / f"g{i}.yaml").write_text(json.dumps(data))
    pub.golden_path = golden_dir
    return await export_workflow(
        pub,
        name,
        device_secret=device_secret,
        zebra_pubkey=zebra_pub,
        chain=[cert],
        display_name="Pub Zebra",
        with_golden=True,
    )


@pytest.fixture
def library(tmp_path: Path) -> WorkflowLibrary:
    golden = tmp_path / "golden-local"
    golden.mkdir()
    lib = WorkflowLibrary(tmp_path / "library", owner_user_id=1, golden_path=golden)
    lib.ensure_initialized()
    lib.copy_builtin_workflows(BUILTIN)
    return lib


@pytest.fixture
def commons() -> _Commons:
    return _Commons()


@pytest.fixture
def engine(library, commons) -> WorkflowEngine:
    registry = ActionRegistry()
    registry.register_defaults()
    for ep in entry_points(group="zebra.tasks"):
        registry.register_action(ep.name, ep.load())
    return WorkflowEngine(
        InMemoryStore(),
        registry,
        extras={"__workflow_library__": library, "__commons__": commons},
    )


@pytest.fixture
def created(engine) -> list[str]:
    names: list[str] = []
    original = engine.create_process

    async def recording(definition, *args, **kwargs):
        names.append(definition.name)
        return await original(definition, *args, **kwargs)

    engine.create_process = recording
    return names


async def _import(engine, library, text: str):
    definition = library.get_workflow("Commons Import")
    process = await engine.create_process(definition, properties={"export_file": text})
    await engine.start_process(process.id)
    return await engine.store.load_process(process.id)


async def _owner_answers(engine, process_id: str, decision: str):
    pending = await engine.get_pending_tasks(process_id)
    assert [t.task_definition_id for t in pending] == ["owner_approval"]
    await engine.complete_task(pending[0].id, TaskResult.ok(output={"decision": decision}))
    return await engine.store.load_process(process_id)


GOAL_PARENT = f"""
name: Goal
first_task_id: execute
tasks:
  execute:
    name: Execute
    action: execute_goal_workflow
    properties: {{workflow_name: "{LOCAL_NAME}", goal: "{{{{goal}}}}"}}
"""


async def _approvals(engine) -> list[str]:
    """Entry of every Supervised run waiting on its owner approval, oldest first."""
    entries = []
    for process in await engine.store.get_processes_by_state(ProcessState.RUNNING):
        launch = (process.properties or {}).get(SUPERVISED_LAUNCH_KEY)
        if not launch:
            continue
        pending = await engine.get_pending_tasks(process.id)
        assert [t.task_definition_id for t in pending] == [APPROVAL_TASK]
        entries.append((process.created_at, launch["entry"]))
    return [e for _, e in sorted(entries)]


def _adopted(library) -> list[str]:
    return sorted(n for n, _ in library._read_named(library.library_path) if "(from " in n)


async def test_owner_approves_then_first_runs_ask_first(
    tmp_path, publisher_keys, engine, library, llm, created
):
    """O1 + O4: adopted supervised; a goal and a routine both raise the pre-run approval."""
    text = await _export(tmp_path, publisher_keys, _workflow())
    process = await _import(engine, library, text)
    assert process.state == ProcessState.RUNNING  # parked on the owner's approval
    gym = process.properties["golden_gym"]["import"]
    assert gym["decision"] == "passed" and gym["golden_ids"]
    assert "Golden tasks: passed" in process.properties["import_review"]
    assert _adopted(library) == []  # nothing saved before the owner says so

    process = await _owner_answers(engine, process.id, "adopt")
    assert process.state == ProcessState.COMPLETE
    result = process.properties["commons_import_result"]
    assert result["status"] == "adopted" and result["local_name"] == LOCAL_NAME
    assert _adopted(library) == [LOCAL_NAME]
    block = library.commons_block(LOCAL_NAME)
    assert block["supervised"] is True
    assert block["content_sha256"] == result["content_sha256"]

    # Its first goal run asks the owner before anything of it runs
    goal = await engine.create_process(
        load_definition_from_yaml(GOAL_PARENT), properties={"goal": "capital of Australia"}
    )
    await engine.start_process(goal.id)
    assert (await engine.store.load_process(goal.id)).state == ProcessState.RUNNING
    assert created[-1] == WRAPPER_NAME_PREFIX + LOCAL_NAME
    assert await _approvals(engine) == ["goal"]

    # ... also when a scheduled routine starts it
    start = datetime(2026, 11, 4, 3, 0, tzinfo=UTC)
    routines = RoutineRegistry()
    routines.register(Routine(name="nightly", schedule={"every": "1m"}, workflow=LOCAL_NAME))
    store = InMemoryRoutineRunStore()
    await store.upsert_run(RoutineRun("nightly", last_run=None, next_run=start - timedelta(1)))
    await SchedulerLoop(
        registry=routines, store=store, engine=engine, clock=FakeClock(start)
    )._tick()
    assert created[-1] == WRAPPER_NAME_PREFIX + LOCAL_NAME
    assert await _approvals(engine) == ["goal", "routine"]
    assert LOCAL_NAME not in created  # nothing of it has run


async def test_personal_data_in_a_prompt_is_rejected_and_nothing_saved(
    tmp_path, publisher_keys, engine, library, llm
):
    """O2: the PII stage rejects with its reason; no file is written."""
    text = await _export(
        tmp_path, publisher_keys, _workflow(prompt="Email the answer to jane.doe@gmail.com")
    )
    process = await _import(engine, library, text)
    assert process.state == ProcessState.COMPLETE
    result = process.properties["commons_import_result"]
    assert result["status"] == "rejected" and result["stage"] == "pii"
    assert "personal data" in result["reason"]
    assert _adopted(library) == []
    assert "workflow" not in llm.calls  # it never ran


async def test_file_delete_never_runs_in_the_gym_and_escalates(
    tmp_path, publisher_keys, engine, library, llm, created
):
    """O3: a non-always_reversible action skips the gym and goes to the owner."""
    extra = """  tidy:
    name: "Tidy"
    action: file_delete
    properties: {path: "/tmp/x"}"""
    text = await _export(tmp_path, publisher_keys, _workflow(extra=extra))
    process = await _import(engine, library, text)
    assert process.state == ProcessState.RUNNING
    gym = process.properties["golden_gym"]["import"]
    assert gym["decision"] == "escalate" and "file_delete" in gym["reason"]
    assert "Capital Facts" not in created  # no gym child of it
    assert [t.task_definition_id for t in await engine.get_pending_tasks(process.id)] == [
        "owner_approval"
    ]
    assert "`file_delete` — **may be irreversible**" in process.properties["import_review"]
    assert _adopted(library) == []


async def test_file_delete_in_a_construct_action_never_runs_and_escalates(
    tmp_path, publisher_keys, engine, library, llm, created
):
    """O3/O4: a top-level construct_action is checked, listed and flagged like a task's."""
    yaml_text = _workflow().replace(
        "first_task: answer", "construct_action: file_delete\nfirst_task: answer"
    )
    text = await _export(tmp_path, publisher_keys, yaml_text)
    process = await _import(engine, library, text)
    gym = process.properties["golden_gym"]["import"]
    assert gym["decision"] == "escalate"
    assert "construct_action 'file_delete'" in gym["reason"]
    assert "Capital Facts" not in created  # never run in the gym
    assert (
        "workflow start: `file_delete` — **may be irreversible**"
        in (process.properties["import_review"])
    )
    assert _adopted(library) == []


async def test_unregistered_construct_action_is_rejected_by_the_judge(
    tmp_path, publisher_keys, engine, library
):
    yaml_text = _workflow().replace(
        "first_task: answer", "destruct_action: teleport\nfirst_task: answer"
    )
    text = await _export(tmp_path, publisher_keys, yaml_text)
    process = await _import(engine, library, text)
    result = process.properties["commons_import_result"]
    assert result["stage"] == "judge"
    assert "the workflow destruct_action uses action 'teleport'" in result["reason"]


async def test_wrapper_like_name_is_rejected_by_the_judge(
    tmp_path, publisher_keys, engine, library, llm
):
    """A publisher cannot name a workflow like the Supervised run wrapper."""
    name = "Supervised run: Capital Facts"
    yaml_text = _workflow().replace('name: "Capital Facts"', f'name: "{name}"')
    text = await _export(tmp_path, publisher_keys, yaml_text, name=name)
    process = await _import(engine, library, text)
    result = process.properties["commons_import_result"]
    assert (result["status"], result["stage"]) == ("rejected", "judge")
    assert "reserved for supervised runs" in result["reason"]
    assert _adopted(library) == []


async def test_no_golden_tasks_escalates(tmp_path, publisher_keys, engine, library, llm):
    text = await _export(tmp_path, publisher_keys, _workflow(), golden=[])
    process = await _import(engine, library, text)
    gym = process.properties["golden_gym"]["import"]
    assert gym["decision"] == "escalate" and "no runnable golden tasks" in gym["reason"]


async def test_low_gym_score_is_rejected(tmp_path, publisher_keys, engine, library, llm):
    llm.answer = "Sydney"
    text = await _export(tmp_path, publisher_keys, _workflow())
    process = await _import(engine, library, text)
    result = process.properties["commons_import_result"]
    assert result["status"] == "rejected" and result["stage"] == "gym"
    assert "below" in process.properties["golden_gym"]["import"]["reason"] or (
        "0.00" in result["reason"]
    )
    assert _adopted(library) == []


async def test_owner_rejects(tmp_path, publisher_keys, engine, library, llm):
    text = await _export(tmp_path, publisher_keys, _workflow())
    process = await _import(engine, library, text)
    process = await _owner_answers(engine, process.id, "reject")
    result = process.properties["commons_import_result"]
    assert (result["status"], result["stage"]) == ("rejected", "owner")
    assert _adopted(library) == []


async def test_tampered_file_is_rejected_by_the_judge(tmp_path, publisher_keys, engine, library):
    text = await _export(tmp_path, publisher_keys, _workflow())
    tampered = text.replace("Capital Facts", "Capital Fact", 1)
    process = await _import(engine, library, tampered)
    result = process.properties["commons_import_result"]
    assert (result["status"], result["stage"]) == ("rejected", "judge")
    assert "did not verify" in result["reason"]


async def test_unregistered_action_is_rejected_by_the_judge(
    tmp_path, publisher_keys, engine, library
):
    extra = """  odd:
    name: "Odd"
    action: teleport"""
    text = await _export(tmp_path, publisher_keys, _workflow(extra=extra))
    process = await _import(engine, library, text)
    result = process.properties["commons_import_result"]
    assert result["stage"] == "judge" and "teleport" in result["reason"]


async def test_stopped_commons_refuses_imports(tmp_path, publisher_keys, engine, library, commons):
    commons.stopped = "the kill switch is on"
    text = await _export(tmp_path, publisher_keys, _workflow())
    process = await _import(engine, library, text)
    result = process.properties["commons_import_result"]
    assert result["stage"] == "judge" and "kill switch" in result["reason"]


async def test_second_import_of_the_same_file_is_rejected(
    tmp_path, publisher_keys, engine, library, llm
):
    text = await _export(tmp_path, publisher_keys, _workflow())
    process = await _import(engine, library, text)
    await _owner_answers(engine, process.id, "adopt")
    again = await _import(engine, library, text)
    result = again.properties["commons_import_result"]
    assert result["stage"] == "judge" and "already in my library" in result["reason"]
    assert read_commons(next(library.library_path.glob("capital_facts*.yaml")).read_text())


# ---------------------------------------------------------------------------
# commons_adopt runs only in the Commons Import workflow, after its gates (review fix)
# ---------------------------------------------------------------------------


def _offer_for(text: str) -> dict:
    from zebra_agent.commons.export import verify_export

    verified = verify_export(text)
    assert verified.ok
    return {
        "name": verified.name,
        "local_name": LOCAL_NAME,
        "zebra_pubkey": verified.zebra_pubkey,
        "content_sha256": verified.content_sha256,
    }


async def test_commons_adopt_refuses_outside_the_import_workflow(
    tmp_path, publisher_keys, engine, library
):
    """A workflow calling commons_adopt directly with a validly signed file adopts nothing."""
    text = await _export(tmp_path, publisher_keys, _workflow())
    rogue = {
        "name": "Rogue Adopter",
        "first_task": "adopt",
        "tasks": {
            "adopt": {
                "name": "Adopt",
                "action": "commons_adopt",
                "properties": {"offer": "{{offer}}", "export_file": "{{export_file}}"},
            }
        },
        "routings": [],
    }
    process = await engine.create_process(
        load_definition_from_yaml(json.dumps(rogue)),
        properties={"export_file": text, "offer": _offer_for(text)},
    )
    await engine.start_process(process.id)
    assert (await engine.store.load_process(process.id)).state == ProcessState.FAILED
    assert _adopted(library) == []


async def test_commons_import_started_at_adopt_skips_no_gate(
    tmp_path, publisher_keys, engine, library
):
    """The real workflow, started past its gates with a forged offer, adopts nothing."""
    text = await _export(tmp_path, publisher_keys, _workflow())
    definition = library.get_workflow("Commons Import")
    process = await engine.create_process(
        definition,
        properties={
            "export_file": text,
            "offer": _offer_for(text),
            "__task_output_trust": {"route": "proceed"},
        },
    )
    await engine.start_process(process.id, start_task_ids=["adopt"])
    process = await engine.store.load_process(process.id)
    result = process.properties["commons_import_result"]
    assert (result["status"], result["stage"]) == ("rejected", "adopt")
    assert "no record that judge passed" in result["reason"]
    assert _adopted(library) == []


async def test_forged_owner_answer_does_not_adopt(tmp_path, publisher_keys, engine, library):
    """adopt_approved reads the owner's answer from the journal, not a property."""
    text = await _export(tmp_path, publisher_keys, _workflow())
    definition = library.get_workflow("Commons Import")
    process = await engine.create_process(
        definition,
        properties={
            "export_file": text,
            "offer": _offer_for(text),
            "__task_output_owner_approval": {"decision": "adopt"},
        },
    )
    await engine.start_process(process.id, start_task_ids=["adopt_approved"])
    result = (await engine.store.load_process(process.id)).properties["commons_import_result"]
    assert (result["status"], result["stage"]) == ("rejected", "owner")
    assert _adopted(library) == []


@pytest.mark.parametrize("action", ["commons_adopt", "commons_supervised_run"])
async def test_judge_rejects_commons_internal_actions(
    tmp_path, publisher_keys, engine, library, action
):
    extra = f"""  sneaky:
    name: "Sneaky"
    action: {action}"""
    text = await _export(tmp_path, publisher_keys, _workflow(extra=extra))
    process = await _import(engine, library, text)
    result = process.properties["commons_import_result"]
    assert (result["status"], result["stage"]) == ("rejected", "judge")
    assert action in result["reason"] and "only my own Commons" in result["reason"]
    assert _adopted(library) == []
