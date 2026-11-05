"""Task actions of the *Skill Share* and *Skill Receive* system workflows (#236, S3b-1).

They read this device's ``SyncService`` from ``context.extras["__commons_sync__"]`` and
the library from ``__workflow_library__``, and fail closed without either: nothing is
proposed, sent or adopted. The logic lives in ``zebra_agent.commons.sync``; these steps
only wire it into the workflows, so every approval is an ordinary human task.

Share: ``skill_share_prepare`` → ``commons_pii_scan`` → ``commons_confidentiality_scan`` →
``commons_sensitivity_check`` → ``skill_share_route`` → (``trust_gate`` sharing | human
task) → ``skill_share_record`` → scans again on the exact bytes → ``skill_send``.

Receive: ``skill_receive_verify`` → both scans → ``trust_gate`` sharing (| human task) →
``skill_receive_adopt`` → (fork) choice task → ``skill_fork_resolve``.
"""

from __future__ import annotations

import logging
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.definitions.loader import load_definition_from_yaml, validate_definition
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.knowledge.extract import resolve_raw

logger = logging.getLogger(__name__)

SYNC_KEY = "__commons_sync__"
LIBRARY_KEY = "__workflow_library__"


def _services(context: ExecutionContext) -> tuple[Any, Any]:
    return context.extras.get(SYNC_KEY), context.extras.get(LIBRARY_KEY)


def _prop(task: TaskInstance, context: ExecutionContext, key: str, default: Any = None) -> Any:
    value = resolve_raw(context, task.properties.get(key, default))
    return default if value in (None, "") else value


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


def _human_output(context: ExecutionContext, task_id: str | None) -> dict[str, Any]:
    if not task_id:
        return {}
    value = context.process.properties.get(f"__task_output_{task_id}")
    return value if isinstance(value, dict) else {}


def _done(context: ExecutionContext, key: str, output: dict[str, Any], route: str) -> TaskResult:
    context.set_process_property(key, output)
    return TaskResult(success=True, output=output, next_route=route)


class SkillSharePrepareAction(TaskAction):
    """Check a share can be proposed and gather what the human will see.

    Properties: ``workflow_name``, ``target_sphere``, ``trigger`` (``runs`` / ``dream`` /
    ``manual``), ``manual``, ``output_key`` (default ``share``).

    Routes ``propose`` (recorded ``proposed``) or ``skip`` (recorded ``skipped``: no sync
    service, may not send, same or unknown sphere, not ``commons_exportable``, already
    shared; or ``blocked``: leak-guard taint on this version or any ancestor, see
    ``leak_kept``). Output: ``{name, sphere,
    own_sphere, observed, tainted_observed, content_sha256, yaml, yaml_sha256, diff, reason,
    manual, title}``.
    """

    description = "Check whether a workflow may be proposed for sharing with another sphere."
    reversibility_hint = "context_dependent"  # appends share decisions to the journal
    inputs = [
        ParameterDef(name="workflow_name", type="string", description="Workflow", required=True),
        ParameterDef(name="target_sphere", type="string", description="Sphere", required=True),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        from zebra_agent.commons import commons_exportable
        from zebra_agent.commons.skill import skill_payload
        from zebra_agent.commons.sync import (
            BLOCKED,
            PROPOSED,
            SKIPPED,
            bytes_sha256,
            diff_text,
            leak_kept,
            record_share,
            share_records,
            version_yaml,
        )

        key = task.properties.get("output_key", "share")
        sync, library = _services(context)
        name = str(_prop(task, context, "workflow_name", ""))
        sphere = str(_prop(task, context, "target_sphere", ""))
        manual = _truthy(_prop(task, context, "manual", False))
        trigger = str(_prop(task, context, "trigger", "runs"))

        content_hash = None

        def skip(reason: str, status: str = SKIPPED) -> TaskResult:
            logger.info("Skill share %r → %s skipped: %s", name, sphere, reason)
            if library is not None:
                record_share(library, name, content_hash, sphere, status, reason=reason)
            return _done(context, key, {"name": name, "sphere": sphere, "reason": reason}, "skip")

        if sync is None or library is None:
            return skip("no sync service or library on this device — failing closed")
        info = await library.get_workflow_info(name)
        content_hash = ((info.commons or {}) if info else {}).get("content_sha256")
        if not sync.can_send:
            return skip(f"sync direction {sync.direction!r} does not allow sending")
        if not sphere or sphere == sync.sphere or sphere not in sync.other_spheres():
            return skip(f"{sphere!r} is not another sphere of this Zebra")
        if info is None or not commons_exportable(info):
            return skip("this workflow may not leave this deployment")
        block = info.commons or {}
        if sphere in (block.get("share_with") or []):
            return skip(f"already shared with {sphere}")
        if leak_kept(library, content_hash, block):
            return skip(
                "the leak guard kept (or never checked) run specifics in this version or "
                "an ancestor",
                BLOCKED,
            )
        text = info.definition_path.read_text()
        payload = skill_payload(text)
        before = None
        for r in share_records(library):
            if r.get("name") == name and r.get("sphere") == sphere and r.get("status") == "sent":
                before = r.get("content_sha256")
        old = version_yaml(library, before) if before and before != content_hash else None
        observed = sync.is_observed(sphere)
        tainted_observed = any(
            sync.is_observed(s) for s in block.get("tainted_by") or [] if isinstance(s, str)
        )
        stats = None
        if library.metrics is not None:
            try:
                stats = await library.metrics.get_stats(name)
            except Exception:  # noqa: BLE001 - the reason just says less
                stats = None
        if manual:
            reason = f"You asked me to share {name} with {sphere}."
        elif trigger == "dream":
            reason = (
                f"I reviewed my workflows in my dream cycle. {name} works well here in "
                f"{sync.sphere}, and I think it would help in {sphere} too."
            )
        else:
            runs = stats.successful_runs if stats else 0
            reason = (
                f"I've run {name} successfully {runs} times here in {sync.sphere}. "
                f"I think it would help in {sphere} too."
            )
        if tainted_observed:
            reason += " It was shaped by runs on a managed device, so I need you to check it."
        output = {
            "name": name,
            "sphere": sphere,
            "own_sphere": sync.sphere,
            "observed": observed,
            "tainted_observed": tainted_observed,
            "content_sha256": content_hash,
            "yaml": payload,
            "yaml_sha256": bytes_sha256(payload),
            "diff": diff_text(old, payload, f"{sphere} copy", "this version"),
            "reason": reason,
            "manual": manual,
            "title": f"Share {name} with {sphere}?",
            "stats": {
                "runs": stats.total_runs if stats else 0,
                "successful_runs": stats.successful_runs if stats else 0,
            },
        }
        record_share(library, name, content_hash, sphere, PROPOSED, reason=trigger)
        return _done(context, key, output, "propose")


class SkillShareRouteAction(TaskAction):
    """Decide who must approve a share (design § S3b step 0).

    Reads ``share`` and ``sensitivity``. Routes:
    - ``never``: sensitive and the target is observed (not a manual share); recorded
      ``sensitive``, nothing is raised.
    - ``observed``: the target is observed or ``tainted_by`` holds an observed sphere →
      the ``observed_share_approval`` human task, which no trust level or freeing skips.
    - ``ask``: sensitive for an unobserved sphere → the share approval task, no autonomy.
    - ``trusted``: otherwise → ``trust_gate (sharing)``.
    """

    description = "Route a share proposal to the right approval (observed, asked or trusted)."
    reversibility_hint = "context_dependent"  # appends a share decision to the journal

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        from zebra_agent.commons.sync import SENSITIVE, record_share

        _sync, library = _services(context)
        share = context.process.properties.get("share") or {}
        sensitivity = context.process.properties.get("sensitivity") or {}
        sensitive = sensitivity.get("sensitive") is not False  # missing = sensitive
        observed = bool(share.get("observed", True))
        manual = bool(share.get("manual"))
        if sensitive and observed and not manual:
            if library is not None:
                record_share(
                    library,
                    share.get("name", ""),
                    share.get("content_sha256"),
                    share.get("sphere", ""),
                    SENSITIVE,
                    reason=sensitivity.get("reason"),
                )
            route = "never"
        elif observed or share.get("tainted_observed"):
            route = "observed"
        elif sensitive:
            route = "ask"
        else:
            route = "trusted"
        output = {"route": route, "sensitive": sensitive, "observed": observed}
        logger.info("Skill share %r → %s: %s", share.get("name"), share.get("sphere"), route)
        return _done(context, task.properties.get("output_key", "share_route"), output, route)


class SkillShareRecordAction(TaskAction):
    """Record the share decision and, if approved, add the sphere to ``share_with``.

    Properties: ``approval_task`` (the human task whose output holds ``decision``
    ``approve`` / ``decline`` and ``visible_on_managed_device``) or ``auto: true`` (an
    earned ``sharing`` level let the trust gate approve). A share to an observed sphere
    needs ``visible_on_managed_device: true``. Approval is void if the workflow changed
    since it was proposed. Routes ``approved`` or ``declined``.
    """

    description = "Record a share approval (adds the sphere to share_with) or a decline."
    reversibility_hint = "context_dependent"  # writes share_with and the journal

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        from zebra_agent.commons.sync import APPROVED, DECLINED, record_share

        key = task.properties.get("output_key", "share_decision")
        _sync, library = _services(context)
        share = context.process.properties.get("share") or {}
        name, sphere = share.get("name", ""), share.get("sphere", "")
        content_hash = share.get("content_sha256")
        auto = _truthy(task.properties.get("auto", False))
        answer = _human_output(context, task.properties.get("approval_task"))
        approved = auto or answer.get("decision") == "approve"
        reason = "approved by earned sharing autonomy" if auto else answer.get("note") or None
        if approved and share.get("observed") and not auto:
            if answer.get("visible_on_managed_device") is not True:
                approved = False
                reason = "not confirmed that it will be visible on a managed device"
        if approved and auto and (share.get("observed") or share.get("tainted_observed")):
            approved, reason = False, "an observed sphere always needs a human approval"
        if library is None:
            approved, reason = False, "no library — failing closed"
        if approved and not library.approve_share(name, sphere, content_hash):
            approved, reason = False, "the workflow changed since it was proposed"
        if library is not None:
            status = APPROVED if approved else DECLINED
            record_share(library, name, content_hash, sphere, status, reason=reason)
        output = {"approved": approved, "reason": reason, "name": name, "sphere": sphere}
        return _done(context, key, output, "approved" if approved else "declined")


class SkillSyncRecordAction(TaskAction):
    """Record a share or receive outcome in the journal (``status``, ``reason`` properties).

    For a share it uses ``share`` (name, hash, target sphere); with ``incoming: true`` it
    uses ``incoming`` (name, hash, sender sphere, event id), so the event is not retried.
    """

    description = "Record a skill-sync outcome (blocked, rejected) in the lineage journal."
    reversibility_hint = "context_dependent"  # appends to the journal

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        from zebra_agent.commons.sync import record_share

        _sync, library = _services(context)
        status = str(task.properties.get("status", "blocked"))
        reason = _prop(task, context, "reason")
        if _truthy(task.properties.get("incoming", False)):
            item = context.process.properties.get("incoming") or {}
            sphere, event_id = item.get("sender_sphere") or "?", item.get("event_id")
        else:
            item = context.process.properties.get("share") or {}
            sphere, event_id = item.get("sphere", ""), None
        if library is not None:
            record_share(
                library,
                item.get("name", ""),
                item.get("content_sha256"),
                sphere,
                status,
                reason=str(reason) if reason else None,
                event_id=event_id,
            )
        return TaskResult.ok(output={"status": status, "reason": reason})


class SkillSendAction(TaskAction):
    """Send an approved workflow as ``SKILL`` events to the approved sphere's devices.

    Needs the send-time scans (``pii_key``, ``confidential_key``) to be clean on the bytes
    being sent (``share.yaml_sha256``). Routes ``sent`` or ``not_sent``.
    """

    description = "Publish an approved workflow to the private sync relay for one sphere."
    reversibility_hint = "always_irreversible"  # it leaves this device

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        from zebra_agent.commons.skill import SkillRefused
        from zebra_agent.commons.sync import BLOCKED, record_share

        key = task.properties.get("output_key", "share_sent")
        sync, library = _services(context)
        share = context.process.properties.get("share") or {}
        props = context.process.properties
        scans = [
            props.get(task.properties.get("pii_key", "send_pii")) or {},
            props.get(task.properties.get("confidential_key", "send_confidential")) or {},
        ]
        if sync is None or library is None:
            return _done(context, key, {"sent": 0, "reason": "no sync service"}, "not_sent")
        if not all(s.get("clean") is True for s in scans):
            record_share(
                library,
                share.get("name", ""),
                share.get("content_sha256"),
                share.get("sphere", ""),
                BLOCKED,
                reason="send-time scan",
            )
            return _done(context, key, {"sent": 0, "reason": "send-time scan"}, "not_sent")
        try:
            events = await sync.send(
                library,
                share.get("name", ""),
                spheres=[share.get("sphere", "")],
                expected_sha256=share.get("content_sha256"),
                scanned_bytes_sha256=share.get("yaml_sha256"),
                stats=share.get("stats"),
            )
        except SkillRefused as e:
            logger.warning("Skill send refused: %s", e)
            return _done(context, key, {"sent": 0, "reason": str(e)}, "not_sent")
        output = {"sent": len(events), "event_ids": [e.id for e in events]}
        return _done(context, key, output, "sent")


class SkillReceiveVerifyAction(TaskAction):
    """Verify a received ``SKILL`` and check its definition before any scan runs.

    Property ``event`` (default ``{{skill_event}}``). Routes ``verified``,
    ``nothing_to_do`` (same hash or an ancestor of the local version) or ``rejected``
    (may not receive, did not verify, invalid definition or unregistered action).
    Output ``incoming``: ``{name, yaml, commons, stats, content_sha256, sender_sphere,
    sender_label, event_id, merge, diff, reason}``.
    """

    description = "Verify a received SKILL event (cert chain, hash, sphere) and its definition."
    reversibility_hint = "context_dependent"  # appends to the journal

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        from zebra_agent.commons.events import Event
        from zebra_agent.commons.sync import (
            NOOP,
            REJECTED,
            STALE,
            diff_text,
            merge_decision,
            record_share,
        )

        key = task.properties.get("output_key", "incoming")
        sync, library = _services(context)
        raw = _prop(task, context, "event", "{{skill_event}}")

        def reject(reason: str, **extra: Any) -> TaskResult:
            output = {"reason": reason, **extra}
            if library is not None and extra.get("event_id"):
                record_share(
                    library,
                    extra.get("name") or "?",
                    extra.get("content_sha256"),
                    extra.get("sender_sphere") or "?",
                    REJECTED,
                    reason=reason,
                    event_id=extra["event_id"],
                )
            logger.warning("Skill receive rejected: %s", reason)
            return _done(context, key, output, "rejected")

        if sync is None or library is None:
            return reject("no sync service or library on this device — failing closed")
        if not sync.can_receive:
            return reject(f"sync direction {sync.direction!r} does not allow receiving")
        try:
            event = Event.from_dict(raw)
        except ValueError as e:
            return reject(f"malformed event: {e}")
        verified = sync.verify(event)
        if not verified.ok:
            return reject(f"did not verify ({verified.reason})", event_id=event.id)
        base = {
            "name": verified.name,
            "content_sha256": verified.content_sha256,
            "sender_sphere": verified.sender_sphere,
            "event_id": event.id,
        }
        try:
            definition = load_definition_from_yaml(verified.yaml)
        except Exception as e:  # noqa: BLE001 - any load failure rejects
            return reject(f"invalid definition: {e}", **base)
        errors = validate_definition(definition)
        if errors:
            return reject(f"invalid definition: {'; '.join(errors)}", **base)
        actions = context.engine.actions if context.engine is not None else None
        missing = sorted(
            {
                t.action
                for t in definition.tasks.values()
                if t.action and (actions is None or not actions.has_action(t.action))
            }
        )
        if missing:
            return reject(f"unregistered actions: {', '.join(missing)}", **base)
        name = verified.name or "untitled"
        local_block = library.commons_block(name) if library._files_named(name) else None
        merge = merge_decision(local_block, verified.commons)
        local_yaml = library.get_workflow_yaml(name) if local_block else None
        output = {
            **base,
            "yaml": verified.yaml,
            "commons": verified.commons,
            "stats": verified.stats,
            "sender_label": verified.sender_label,
            "merge": merge,
            "diff": diff_text(local_yaml, verified.yaml, "this device", verified.sender_sphere),
            "reason": (
                f"My {verified.sender_sphere} device shared {name} with this sphere. "
                + (
                    "It is new here."
                    if merge == "new"
                    else "It is a newer version of my copy."
                    if merge == "fast_forward"
                    else "Both copies changed, so you will choose which to keep."
                )
            ),
        }
        if merge in (NOOP, STALE):
            record_share(
                library,
                name,
                verified.content_sha256,
                verified.sender_sphere or "?",
                "received",
                reason=merge,
                event_id=event.id,
            )
            return _done(context, key, output, "nothing_to_do")
        return _done(context, key, output, "verified")


class SkillReceiveAdoptAction(TaskAction):
    """Adopt a verified, scanned, approved ``SKILL`` by lineage (``SyncService.apply_received``).

    Property ``approval_task``: a human task whose output ``decision`` must be ``approve``
    (absent when the trust gate let it through). Routes ``adopted``, ``fork``, ``declined``
    or ``refused``.
    """

    description = "Adopt a received workflow into the library by lineage (merge or fork)."
    reversibility_hint = "context_dependent"  # writes the library

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        from zebra_agent.commons.skill import SkillRefused, SkillVerification
        from zebra_agent.commons.sync import DECLINED, record_share
        from zebra_agent.library import AdoptionRefused

        key = task.properties.get("output_key", "received")
        sync, library = _services(context)
        item = context.process.properties.get("incoming") or {}
        approval = task.properties.get("approval_task")
        if approval and _human_output(context, approval).get("decision") != "approve":
            if library is not None:
                record_share(
                    library,
                    item.get("name", ""),
                    item.get("content_sha256"),
                    item.get("sender_sphere") or "?",
                    DECLINED,
                    event_id=item.get("event_id"),
                )
            return _done(context, key, {"action": "declined"}, "declined")
        if sync is None or library is None:
            return _done(context, key, {"action": "refused", "reason": "no sync"}, "refused")
        verified = SkillVerification(
            ok=True,
            reason="ok",
            name=item.get("name"),
            yaml=item.get("yaml"),
            commons=item.get("commons"),
            stats=item.get("stats") or {},
            content_sha256=item.get("content_sha256"),
            sender_sphere=item.get("sender_sphere"),
            event_id=item.get("event_id"),
        )
        try:
            result = sync.apply_received(library, verified)
        except (AdoptionRefused, SkillRefused, ValueError) as e:
            logger.warning("Skill receive: adoption refused: %s", e)
            return _done(context, key, {"action": "refused", "reason": str(e)}, "refused")
        route = "fork" if result["action"] == "fork" else "adopted"
        return _done(context, key, result, route)


class SkillForkResolveAction(TaskAction):
    """Apply the human's fork choice (``keep``: ``mine`` / ``theirs`` / ``both``)."""

    description = "Resolve a sync fork as the human chose."
    reversibility_hint = "context_dependent"  # retires or renames library files

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        _sync, library = _services(context)
        received = context.process.properties.get("received") or {}
        answer = _human_output(context, task.properties.get("choice_task", "fork_choice"))
        keep = answer.get("keep")
        if library is None or keep not in ("mine", "theirs", "both"):
            return TaskResult.fail(f"cannot resolve fork (choice {keep!r})")
        try:
            current = library.resolve_fork(received.get("name"), received.get("fork_name"), keep)
        except ValueError as e:
            return TaskResult.fail(str(e))
        return TaskResult.ok(output={"keep": keep, "current": current})
