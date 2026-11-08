"""``commons_attest_import``: the outcome is read from the step journal (#232, S5)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from zebra_tasks.commons.attest_actions import VOICE, CommonsAttestImportAction, import_outcome
from zebra_tasks.commons.guard import COMMONS_INTERNAL_ACTIONS


def _step(route: str | None, **changed):
    return SimpleNamespace(next_route=route, changed=changed)


PASSED = {"judge": _step("proceed"), "pii_scan": _step("clean")}


@pytest.mark.parametrize(
    "steps,expected",
    [
        (
            {
                **PASSED,
                "ethics": _step("proceed"),
                "gym": _step("passed"),
                "adopt": _step("adopted"),
            },
            ("adopted", "adopt", "adopted", "passed-checks"),
        ),
        (
            {**PASSED, "adopt_approved": _step("adopted")},
            ("adopted", "adopt", "adopted", "owner-approved"),
        ),
        (
            {
                "judge": _step("proceed"),
                "pii_scan": _step(
                    "rejected",
                    pii_scan={"failed_closed": False, "findings": [{"kind": "contact"}]},
                ),
            },
            ("rejected", "pii", "pii-found", None),
        ),
        (
            {
                "judge": _step("proceed"),
                "pii_scan": _step("rejected", pii_scan={"failed_closed": True, "findings": []}),
            },
            ("rejected", "pii", "rejected-pii", None),
        ),
        ({**PASSED, "ethics": _step("reject")}, ("rejected", "ethics", "rejected-ethics", None)),
        (
            {**PASSED, "ethics": _step("proceed"), "gym": _step("rejected")},
            ("rejected", "gym", "rejected-gym", None),
        ),
        ({"judge": _step("reject")}, ("rejected", "judge", None, None)),
        ({**PASSED, "adopt_approved": _step("declined")}, ("rejected", "owner", None, None)),
        ({**PASSED, "adopt": _step("refused")}, ("rejected", "adopt", None, None)),
        ({}, ("rejected", "judge", None, None)),
    ],
)
def test_import_outcome_from_the_journal(steps, expected):
    outcome = import_outcome(steps)
    assert (outcome["status"], outcome["stage"], outcome["label"], outcome["reason"]) == expected


def test_every_outcome_has_a_voice_line_and_the_action_is_internal():
    for key in ("adopted", "pii-found", "rejected-pii", "rejected-ethics", "rejected-gym"):
        assert VOICE[key].startswith("I ")
    for key in ("judge", "owner", "adopt"):
        assert VOICE[key]
    assert "commons_attest_import" in COMMONS_INTERNAL_ACTIONS
    assert CommonsAttestImportAction.reversibility_hint == "always_irreversible"


async def test_refuses_outside_the_import_workflow():
    from zebra.core.models import ProcessDefinition, TaskDefinition

    definition = ProcessDefinition(
        id="x",
        name="Mine",
        first_task_id="a",
        tasks={"a": TaskDefinition(id="a", name="A", action="commons_attest_import")},
    )
    context = SimpleNamespace(process_definition=definition, extras={})
    result = await CommonsAttestImportAction().run(SimpleNamespace(properties={}), context)
    assert not result.success
