"""Judged import of a signed Commons workflow file (Zebra Commons S3, #230).

The actions of the *Commons Import* workflow (``zebra-agent/workflows/commons_import.yaml``):

- ``commons_judge_import``: verify the signed file, validate the YAML, require every
  action to be registered and the local name to be free; build the ``offer``.
- ``commons_import_review``: the markdown the owner reads on the approval task.
- ``commons_adopt``: after the trust gate (or the owner's approval) adopt it through
  ``WorkflowLibrary.save(writer="adopt")`` as ``<name> (from <publisher>)``, supervised.
- ``commons_record_import``: record the outcome, adopted or rejected with its stage and
  reason, as ``commons_import_result``.

The personal-data scan, ethics gate, gym (import mode) and trust gate between them are
the existing ``commons_pii_scan``, ``ethics_gate``, ``run_golden_gym`` and ``trust_gate``.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.commons.supervised import commons_stop_reason, workflow_actions
from zebra_tasks.knowledge.extract import resolve_raw

logger = logging.getLogger(__name__)

PROCEED = "proceed"
REJECT = "reject"
ADOPTED = "adopted"
REFUSED = "refused"
DECLINED = "declined"
DECISION_ADOPT = "adopt"
RESULT_KEY = "commons_import_result"
_MAX_DISPLAY_NAME = 60


async def _held_events(extras: dict[str, Any]) -> list:
    """Certs and revokes this deployment holds, from the ``__commons__`` service."""
    getter = getattr(extras.get("__commons__"), "held_events", None)
    if not callable(getter):
        return []
    return list(await getter())


def publisher_label(display_name: str | None, zebra_pubkey: str | None) -> str:
    """A short, safe publisher name for the local workflow name.

    The signed display name, tidied (one line, no brackets, at most 60 characters), or
    the publisher key's fingerprint when it has none.
    """
    from zebra_agent.commons.identity import fingerprint

    label = re.sub(r"[\s()\[\]{}]+", " ", display_name or "").strip()[:_MAX_DISPLAY_NAME].strip()
    if label:
        return label
    return fingerprint(zebra_pubkey) if zebra_pubkey else "unknown Zebra"


def _verify(text: Any, expected_zebra: Any, held: list) -> Any:
    from zebra_agent.commons.export import verify_export

    expected = expected_zebra.strip().lower() if isinstance(expected_zebra, str) else ""
    if not expected or "{{" in expected:  # unset run input
        expected = None
    return verify_export(
        text if isinstance(text, str | bytes) else "", expected_zebra=expected, revocations=held
    )


def offer_summary(offer: dict[str, Any]) -> str:
    """Markdown describing an offer: publisher, hash, actions (flagged), golden tasks."""
    lines = [
        f"**{offer['name']}** from **{offer['publisher']}** "
        f"(Zebra `{str(offer.get('zebra_pubkey') or '')[:16]}…`)",
        f"- Content hash: `{str(offer.get('content_sha256') or '')[:16]}…`",
        f"- Would be added as: **{offer['local_name']}**, supervised",
        f"- Golden tasks shipped: {len(offer.get('golden_tasks') or [])}",
        "",
        "**Actions**",
        "",
    ]
    for a in offer.get("actions") or []:
        flag = f" — **{a['flag']}**" if a.get("flag") else ""
        lines.append(f"- {a['task']}: `{a['action']}`{flag}")
    return "\n".join(lines)


class CommonsJudgeImportAction(TaskAction):
    """Verify and validate a signed workflow file; route ``proceed`` or ``reject``."""

    description = (
        "Check a signed Commons workflow file before import: signature and device chain, "
        "valid YAML, every action registered, local name free. Builds the offer."
    )
    # Reads only: verification, parsing and library lookups.
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="export_file", type="string", description="The file's text", required=True
        ),
        ParameterDef(
            name="expected_zebra",
            type="string",
            description="Accept only this publisher (hex Zebra pubkey)",
            required=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property for the offer",
            required=False,
            default="offer",
        ),
    ]
    outputs = [
        ParameterDef(name="offer", type="dict", description="The judged offer", required=False),
        ParameterDef(name="reason", type="string", description="Why rejected", required=False),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Judge the file; store the offer (or the rejection) and route."""
        reason, offer = await self._judge(task, context)
        if reason:
            logger.info("Commons import rejected by the judge: %s", reason)
            context.set_process_property("import_judgement", {"stage": "judge", "reason": reason})
            return TaskResult(success=True, output={"reason": reason}, next_route=REJECT)
        context.set_process_property(task.properties.get("output_key", "offer"), offer)
        context.set_process_property("import_judgement", {"stage": "judge", "reason": "ok"})
        return TaskResult(success=True, output={"offer": offer}, next_route=PROCEED)

    async def _judge(
        self, task: TaskInstance, context: ExecutionContext
    ) -> tuple[str | None, dict[str, Any] | None]:
        stopped = await commons_stop_reason(context.extras)
        if stopped:
            return f"the Commons is stopped: {stopped}", None
        text = resolve_raw(context, task.properties.get("export_file"))
        expected = resolve_raw(context, task.properties.get("expected_zebra"))
        verified = _verify(text, expected, await _held_events(context.extras))
        if not verified.ok:
            return f"the file did not verify ({verified.reason})", None
        try:
            definition = load_definition_from_yaml(verified.yaml)
        except Exception as e:  # noqa: BLE001
            return f"the workflow is not valid: {e}", None
        registry = context.engine.actions
        for task_id, task_def in definition.tasks.items():
            for action in (task_def.action, task_def.construct_action, task_def.destruct_action):
                if action and not registry.has_action(action):
                    return f"task '{task_id}' uses action '{action}', which I do not have", None
        publisher = publisher_label(verified.display_name, verified.zebra_pubkey)
        local_name = f"{verified.name} (from {publisher})"
        library = context.extras.get("__workflow_library__")
        if library is not None:
            block = library.commons_block(local_name)
            if block is not None:
                if block.get("content_sha256") == verified.content_sha256:
                    return f"{local_name!r} is already in my library", None
                return f"a different workflow is already named {local_name!r}", None
        offer = {
            "name": verified.name,
            "local_name": local_name,
            "publisher": publisher,
            "zebra_pubkey": verified.zebra_pubkey,
            "content_sha256": verified.content_sha256,
            "yaml": verified.yaml,
            "commons": verified.commons,
            "golden_tasks": verified.golden_tasks,
            "actions": workflow_actions(definition, registry),
        }
        offer["summary"] = offer_summary(offer)
        return None, offer


class CommonsImportReviewAction(TaskAction):
    """Write the owner's review of an import (``import_review``) from what the gates found."""

    description = (
        "Summarise an import for the owner's approval: the offer, the personal-data scan, "
        "the ethics review, the gym and the trust gate."
    )
    # Reads process properties and writes one of this run's properties.
    reversibility_hint = "always_reversible"

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Compose the review markdown."""
        props = context.process.properties
        offer = props.get("offer") or {}
        lines = [offer.get("summary") or "(no offer)", "", "**What my checks found**", ""]
        pii = props.get("pii_scan")
        if isinstance(pii, dict):
            found = "none found" if pii.get("clean") else pii.get("reason")
            lines.append(f"- Personal data: {found}")
        ethics = props.get("import_ethics")
        if isinstance(ethics, dict):
            verdict = "approved" if ethics.get("approved") else "not approved"
            if props.get("dilemma_display"):
                verdict = "a dilemma I want you to decide"
            lines.append(f"- Ethics: {verdict}. {ethics.get('overall_reasoning') or ''}".rstrip())
        gym = (props.get("golden_gym") or {}).get("import")
        if isinstance(gym, dict):
            lines.append(f"- Golden tasks: {gym.get('decision')} — {gym.get('reason')}")
        else:
            lines.append("- Golden tasks: not run")
        trust = props.get("import_trust")
        if isinstance(trust, dict):
            lines.append(f"- Trust (sharing): {trust.get('level')} — {trust.get('reason') or ''}")
        review = "\n".join(lines)
        context.set_process_property(task.properties.get("output_key", "import_review"), review)
        return TaskResult.ok(output={"review": review})


class CommonsAdoptAction(TaskAction):
    """Adopt a judged import into the library, supervised; route ``adopted`` / ``refused``."""

    description = (
        "Add a judged, approved Commons workflow to the library through "
        "WorkflowLibrary.save(writer='adopt'): provenance kept, renamed "
        "'<name> (from <publisher>)', supervised until a human clears it."
    )
    # Writes the workflow library.
    reversibility_hint = "context_dependent"

    inputs = [
        ParameterDef(name="offer", type="dict", description="'{{offer}}'", required=True),
        ParameterDef(
            name="export_file",
            type="string",
            description="The file's text, verified again before adopting",
            required=True,
        ),
        ParameterDef(
            name="approval_task",
            type="string",
            description="Owner approval task whose decision must be 'adopt', if any",
            required=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property for the result",
            required=False,
            default="commons_adoption",
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Adopt, or refuse with a reason."""
        key = task.properties.get("output_key", "commons_adoption")
        approval = task.properties.get("approval_task")
        if approval:
            answer = context.process.properties.get(f"__task_output_{approval}")
            decision = answer.get("decision") if isinstance(answer, dict) else None
            if decision != DECISION_ADOPT:
                note = answer.get("note") if isinstance(answer, dict) else ""
                reason = "the owner rejected it" + (f": {note}" if note else "")
                return self._result(context, key, DECLINED, reason)
        reason, result = await self._adopt(task, context)
        if reason:
            return self._result(context, key, REFUSED, reason)
        return self._result(context, key, ADOPTED, "adopted", result)

    @staticmethod
    def _result(
        context: ExecutionContext,
        key: str,
        route: str,
        reason: str,
        extra: dict[str, Any] | None = None,
    ) -> TaskResult:
        output = {"route": route, "reason": reason, **(extra or {})}
        context.set_process_property(key, output)
        logger.info("Commons adoption: %s (%s)", route, reason)
        return TaskResult(success=True, output=output, next_route=route)

    async def _adopt(
        self, task: TaskInstance, context: ExecutionContext
    ) -> tuple[str | None, dict[str, Any] | None]:
        from zebra_agent.commons.export import adopt_export

        stopped = await commons_stop_reason(context.extras)
        if stopped:
            return f"the Commons is stopped: {stopped}", None
        offer = resolve_raw(context, task.properties.get("offer"))
        if not isinstance(offer, dict) or not offer.get("local_name"):
            return "no judged offer to adopt", None
        library = context.extras.get("__workflow_library__")
        if library is None:
            return "no workflow library to adopt into", None
        text = resolve_raw(context, task.properties.get("export_file"))
        verified = _verify(text, offer.get("zebra_pubkey"), await _held_events(context.extras))
        if not verified.ok or verified.content_sha256 != offer.get("content_sha256"):
            return f"the file no longer verifies as the judged offer ({verified.reason})", None
        try:
            path = adopt_export(library, verified, name=offer["local_name"])
        except ValueError as e:  # AdoptionRefused, ExportRefused
            return f"the library refused it: {e}", None
        name = offer["local_name"]
        return None, {
            "name": name,
            "file": getattr(path, "name", str(path)),
            "content_sha256": verified.content_sha256,
            "supervised": library.is_supervised(name),
        }


class CommonsRecordImportAction(TaskAction):
    """Record how an import ended as ``commons_import_result`` (adopted, or why rejected)."""

    description = "Record a Commons import's outcome: adopted, or rejected with stage and reason."
    # Writes only this run's own result property.
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(name="status", type="string", description="adopted / rejected", required=True),
        ParameterDef(name="stage", type="string", description="Gate that decided", required=True),
        ParameterDef(name="reason", type="string", description="Why", required=False),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Store and log the result."""
        props = context.process.properties
        offer = props.get("offer") if isinstance(props.get("offer"), dict) else {}
        reason = resolve_raw(context, task.properties.get("reason") or "")
        if not isinstance(reason, str) or not reason.strip() or "{{" in reason:
            reason = "no reason recorded"
        result = {
            "status": str(task.properties.get("status") or "rejected"),
            "stage": str(task.properties.get("stage") or "unknown"),
            "reason": reason.strip()[:2000],
            "workflow": offer.get("name"),
            "local_name": offer.get("local_name"),
            "publisher": offer.get("publisher"),
            "content_sha256": offer.get("content_sha256"),
        }
        context.set_process_property(RESULT_KEY, result)
        logger.info(
            "Commons import %s at %s: %s (%s)",
            result["status"],
            result["stage"],
            result["reason"][:200],
            result["local_name"] or "-",
        )
        return TaskResult.ok(output=result)
