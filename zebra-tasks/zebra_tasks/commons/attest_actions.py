"""``commons_attest_import``: the last step of *Commons Import* (#232, S5).

Records how the judged import of a public ``OFFER`` ended on the offer's row and publishes an
``ATTEST`` of it through ``extras["__commons_exchange__"]``:

- ``adopted`` when ``commons_adopt`` routed ``adopted``;
- ``pii-found`` / ``rejected-pii`` when the personal-data scan rejected it (findings / failed
  closed), ``rejected-ethics`` when ethics did, ``rejected-gym`` when the gym did;
- nothing public for a judge rejection, the owner's "no" or a refused adoption: those are
  local and say nothing about the workflow.

The outcome and the import's source come from the **step journal**, never a process property.
Only an import whose judge recorded ``import_source.source == "offer"`` is attested: a file
shared privately is never mentioned publicly, not even by hash. The attestation carries only
the label and a fixed reason; the gates' own reasoning stays in the local judgement. A
failure here is logged and never fails the import.
"""

from __future__ import annotations

import logging
from typing import Any

from zebra.core.models import ProcessEvent, TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.commons.guard import completed_steps, is_import_workflow

logger = logging.getLogger(__name__)

EXCHANGE_KEY = "__commons_exchange__"
RECORD_STEPS = (
    "record_adopted",
    "rejected_judge",
    "rejected_pii",
    "rejected_ethics",
    "rejected_gym",
    "rejected_owner",
    "rejected_adopt",
)

#: Zebra's own words for each outcome, shown on /commons/ (local only, never published).
VOICE = {
    "adopted": (
        "I adopted it. It passed my checks, and it stays supervised until you have approved "
        "its first runs."
    ),
    "pii-found": "I turned it down: I found personal data in it.",
    "rejected-pii": "I turned it down: I could not finish checking it for personal data.",
    "rejected-ethics": "I turned it down: my ethics review did not approve it.",
    "rejected-gym": "I turned it down: it failed its own golden tasks when I tried them.",
    "judge": "I could not take it: it failed my first checks.",
    "owner": "You chose not to adopt it, so I left it out.",
    "adopt": "I could not add it to my library.",
}


def import_outcome(steps: dict[str, ProcessEvent]) -> dict[str, Any]:
    """``{status, stage, label, reason}`` of a finished import, from the step journal.

    ``label`` is the attestation label (None: nothing to attest) and ``reason`` its fixed
    reason. Fails closed: no record of an adoption is a rejection.
    """
    for task_id, reason in (("adopt", "passed-checks"), ("adopt_approved", "owner-approved")):
        event = steps.get(task_id)
        if event is not None and event.next_route == "adopted":
            return {"status": "adopted", "stage": "adopt", "label": "adopted", "reason": reason}
    pii = steps.get("pii_scan")
    if pii is not None and pii.next_route == "rejected":
        scan = pii.changed.get("pii_scan") or pii.changed.get("__task_output_pii_scan") or {}
        found = (
            isinstance(scan, dict) and scan.get("failed_closed") is False and scan.get("findings")
        )
        label = "pii-found" if found else "rejected-pii"
        return {"status": "rejected", "stage": "pii", "label": label, "reason": None}
    for task_id, route, label, stage in (
        ("ethics", "reject", "rejected-ethics", "ethics"),
        ("gym", "rejected", "rejected-gym", "gym"),
    ):
        event = steps.get(task_id)
        if event is not None and event.next_route == route:
            return {"status": "rejected", "stage": stage, "label": label, "reason": None}
    judge = steps.get("judge")
    adopt = steps.get("adopt_approved") or steps.get("adopt")
    if judge is None or judge.next_route != "proceed":
        stage = "judge"
    elif adopt is not None and adopt.next_route == "declined":
        stage = "owner"
    else:
        stage = "adopt"
    return {"status": "rejected", "stage": stage, "label": None, "reason": None}


def _local_reason(steps: dict[str, ProcessEvent]) -> str:
    for task_id in RECORD_STEPS:
        event = steps.get(task_id)
        result = event.changed.get("commons_import_result") if event is not None else None
        if isinstance(result, dict) and isinstance(result.get("reason"), str):
            return result["reason"][:2000]
    return ""


class CommonsAttestImportAction(TaskAction):
    """Record a judged import of a public offer and attest its outcome (never fails)."""

    description = (
        "Last step of Commons Import: record the outcome on the offer and publish a signed "
        "ATTEST (adopted, or the rejecting gate) when the import came from a public offer."
    )
    # Publishes a signed event to the public Commons.
    reversibility_hint = "always_irreversible"

    outputs = [
        ParameterDef(name="attested", type="boolean", description="Published", required=True),
        ParameterDef(name="label", type="string", description="Attestation label", required=False),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Read the journal, update the offer, attest."""
        if not is_import_workflow(context.process_definition):
            logger.warning("commons_attest_import refused outside the Commons Import workflow")
            return TaskResult.fail("commons_attest_import runs only in Commons Import")
        steps = await completed_steps(context)
        judge = steps.get("judge")
        source = judge.changed.get("import_source") if judge is not None else None
        outcome = import_outcome(steps)
        if isinstance(source, dict) and source.get("verified") is not True:
            outcome["label"] = None  # an offer that did not verify is never attested
        output: dict[str, Any] = {"attested": False, "label": outcome["label"], **outcome}
        if not isinstance(source, dict) or source.get("source") != "offer":
            output["skipped"] = "not an offer"
            return TaskResult.ok(output=output)
        sha = source.get("content_sha256")
        exchange = context.extras.get(EXCHANGE_KEY)
        if exchange is None or not isinstance(sha, str):
            logger.warning("Commons: no exchange; import of %s… not recorded", str(sha)[:12])
            output["skipped"] = "Commons publishing is off"
            return TaskResult.ok(output=output)
        voice_key = outcome["label"] or outcome["stage"]
        judgement = {
            "stage": outcome["stage"],
            "label": outcome["label"],
            "voice": VOICE.get(voice_key, ""),
            "reason": _local_reason(steps),
            "process_id": context.process.id,
        }
        try:
            published = await exchange.record_import(
                sha,
                status=outcome["status"],
                label=outcome["label"],
                reason=outcome["reason"],
                judgement=judgement,
            )
        except Exception as e:  # noqa: BLE001 - attesting never fails the import
            logger.warning("Commons: attesting the import of %s… failed: %s", sha[:12], e)
            output["error"] = str(e)[:300]
            return TaskResult.ok(output=output)
        if published:
            output.update(attested=True, event_id=published.get("event_id"))
        return TaskResult.ok(output=output)
