"""Task actions of the *Commons Offer* system workflow (#231, S4).

``commons_offer.yaml``: ``commons_prepare_offer`` → ``commons_pii_scan`` (YAML, golden tasks,
summary) → ``ethics_gate`` (plan_review) → ``commons_offer_route`` → ``trust_gate`` (sharing,
owner-governed) or the owner's approval → ``commons_offer_record`` → ``commons_publish`` →
``commons_record_offer``.

They read the publisher from ``context.extras["__commons_publisher__"]`` (only injected when
``ZEBRA_COMMONS_RELAYS`` is set) and the library from ``__workflow_library__``, and fail closed
without either. ``commons_offer_record`` (writes ``share_with``) and ``commons_publish`` (puts
the workflow on a public relay) trust no process property: they run only inside the shipped
workflow (``guard.is_offer_workflow``), take the offer from the step journal entry of
``prepare`` and check the journal for every gate and the owner's answer.
"""

from __future__ import annotations

import logging
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.agent.definition_actions import definition_actions
from zebra_tasks.commons.guard import completed_steps, human_answer, is_offer_workflow
from zebra_tasks.commons.supervised import commons_stop_reason
from zebra_tasks.knowledge.extract import resolve_raw

logger = logging.getLogger(__name__)

PUBLISHER_KEY = "__commons_publisher__"
LIBRARY_KEY = "__workflow_library__"
METRICS_KEY = "__metrics_store__"
RESULT_KEY = "commons_offer_result"
PREPARE_TASK = "prepare"
DECISION_PUBLISH = "publish"

#: What the journal must show before the offer is approved without the owner, or published.
_GATES_TO_OWNER = {PREPARE_TASK: "propose", "pii_scan": "clean"}
_GATES_UNATTENDED = {**_GATES_TO_OWNER, "ethics": "proceed", "route": "trusted", "trust": "proceed"}

SUMMARY_SYSTEM = """You write the public listing of a workflow that another person's AI
assistant may adopt. You see only the workflow definition and its numeric run statistics.

Be honest and plain: say what the workflow does, not what it might do. Never claim results the
statistics do not show. Never include names, places, dates, accounts, or anything about the
person who used it; describe the kind of goal instead.

Reply with JSON only:
{"summary": "1-3 sentences: what it does and how well (from the statistics)",
 "use_when": "one sentence: the kind of goal it fits",
 "golden_tasks": [{"goal": "a realistic sample goal", "expected": "what a good result looks like",
                   "criteria": ["checkable pass criterion", "..."]}]}
Write 1-3 golden tasks: generic sample goals someone else could run to test the workflow."""


def _services(context: ExecutionContext) -> tuple[Any, Any]:
    return context.extras.get(PUBLISHER_KEY), context.extras.get(LIBRARY_KEY)


def _done(context: ExecutionContext, key: str, output: dict[str, Any], route: str) -> TaskResult:
    context.set_process_property(key, output)
    return TaskResult(success=True, output=output, next_route=route)


async def _runs_and_stats(library: Any, context: ExecutionContext, name: str) -> tuple[Any, Any]:
    """``(WorkflowStats | None, gym mean | None)`` from the metrics store."""
    metrics = getattr(library, "metrics", None) or context.extras.get(METRICS_KEY)
    if metrics is None:
        return None, None
    stats = await metrics.get_stats(name)
    gym = None
    getter = getattr(metrics, "get_gym_scores", None)
    if callable(getter):
        try:
            scores = await getter(workflow_name=name, variant="current", limit=20)
            values = [s.score for s in scores if s.score is not None]
            gym = sum(values) / len(values) if values else None
        except Exception as e:  # noqa: BLE001 - the offer just says less
            logger.info("Commons offer: no gym scores for %r: %s", name, e)
    return stats, gym


async def _write_listing(
    task: TaskInstance, context: ExecutionContext, yaml_text: str, stats: dict[str, Any]
) -> dict[str, Any]:
    """The low-tier LLM's ``{summary, use_when, golden_tasks}``; raises on any failure."""
    from zebra_tasks.llm.base import Message
    from zebra_tasks.llm.client import get_llm, model_for
    from zebra_tasks.llm.structured import complete_json

    llm = get_llm(model_for(task, context, default="low"), context)
    prompt = f"## Run statistics\n{stats}\n\n## Workflow definition\n```yaml\n{yaml_text}\n```"
    reply = await complete_json(
        llm,
        [Message.system(SUMMARY_SYSTEM), Message.user(prompt)],
        temperature=0.2,
        max_tokens=1500,
    )
    if not isinstance(reply, dict):
        raise ValueError("the listing reply is not a JSON object")
    return reply


def _review(name: str, content: dict[str, Any], taint: list[str], parent: str | None) -> str:
    stats = content["stats"]
    lines = [
        f"**{name}**: {content['summary']}",
        "",
        f"Use when: {content['use_when'] or '-'}",
        "",
        f"Runs here: {stats['runs']}, success rate {stats['success_rate']:.0%}, "
        f"average rating {stats['avg_rating'] if stats['avg_rating'] is not None else '-'}, "
        f"gym score {stats['gym_score'] if stats['gym_score'] is not None else '-'}.",
        f"Actions: {', '.join(content['actions']) or '-'}.",
        "Parent: "
        + (
            f"my public offer {parent[:12]}…"
            if parent
            else "none shown (first public version; private ancestors are never named)"
        ),
        "",
        "Golden tasks other Zebras will test it on:",
    ]
    for g in content["golden_tasks"]:
        lines.append(f"- {g['goal']} (pass: {'; '.join(g['criteria'])})")
    if taint:
        lines += [
            "",
            f"It was shaped by runs in {', '.join(taint)}, a sphere managed by someone else "
            "(or unknown here), so only you can approve this.",
        ]
    lines += ["", "```yaml", content["yaml"].rstrip(), "```"]
    return "\n".join(lines)


class CommonsPrepareOfferAction(TaskAction):
    """Check a workflow may be offered and build what will be scanned, reviewed and published.

    Routes ``propose`` (output ``offer``: ``{name, content_sha256, content, yaml, listing,
    golden_tasks, observed_taint, parent, review}``) or ``refuse`` (``{name, reason}``): no
    publisher or library, the Commons stopped, the ``offer_refusal`` preconditions (not
    exportable, leak guard kept / error, fewer than ``MIN_RUNS_TO_OFFER`` runs), already
    offered, or no honest listing (no LLM, an unusable reply, bad golden tasks).
    """

    description = (
        "Check a workflow may be offered publicly (exportable, leak-free, enough runs) and "
        "build its OFFER content: canonical YAML, stats, actions, summary and golden tasks."
    )
    reversibility_hint = "always_reversible"  # reads the library and metrics, one LLM call
    inputs = [
        ParameterDef(name="workflow_name", type="string", description="Workflow", required=True),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        from zebra_agent.commons.offer import (
            OfferRefused,
            offer_content,
            offer_refusal,
            offer_stats,
            public_parent,
        )
        from zebra_agent.provenance import relabel

        key = task.properties.get("output_key", "offer")
        name = str(resolve_raw(context, task.properties.get("workflow_name")) or "")
        publisher, library = _services(context)

        def refuse(reason: str) -> TaskResult:
            logger.info("Commons offer of %r refused: %s", name, reason)
            return _done(context, key, {"name": name, "reason": reason}, "refuse")

        if publisher is None or library is None:
            return refuse("Commons publishing is off on this device (no ZEBRA_COMMONS_RELAYS)")
        stopped = await commons_stop_reason(context.extras)
        if stopped:
            return refuse(f"the Commons is stopped: {stopped}")
        info = await library.get_workflow_info(name)
        try:
            stats, gym = await _runs_and_stats(library, context, name)
        except Exception as e:  # noqa: BLE001 - no evidence, no offer
            return refuse(f"could not read the run statistics: {e}")
        runs = stats.total_runs if stats else 0
        reason = offer_refusal(info, library, runs)
        if reason:
            return refuse(reason)
        block = info.commons or {}
        digest = block.get("content_sha256")
        if digest in await publisher.offered_hashes():
            return refuse("this version is already offered")
        try:
            yaml_text = relabel(info.definition_path.read_text())
            definition = load_definition_from_yaml(yaml_text)
        except Exception as e:  # noqa: BLE001 - unreadable, unhashable or invalid
            return refuse(f"the workflow does not load: {e}")
        actions = sorted({d.action for d in definition_actions(definition)})
        numbers = offer_stats(stats, gym)
        try:
            listing = await _write_listing(task, context, yaml_text, numbers)
        except Exception as e:  # noqa: BLE001 - no honest summary, no offer
            return refuse(f"could not write an honest summary: {str(e)[:300]}")
        golden = [t.to_dict() for t in library.list_golden_tasks(name)][:3]
        golden = golden or list(listing.get("golden_tasks") or [])
        try:
            content = offer_content(
                name=info.name,
                summary=str(listing.get("summary") or ""),
                use_when=str(listing.get("use_when") or info.use_when or ""),
                stats=numbers,
                actions=actions,
                golden_tasks=golden,
                yaml=yaml_text,
            )
        except OfferRefused as e:
            return refuse(str(e))
        taint = publisher.observed_taint(block)
        parent = public_parent(block, await publisher.public_hashes())
        output = {
            "name": info.name,
            "content_sha256": digest,
            "content": content,
            "yaml": yaml_text,
            "golden_tasks": content["golden_tasks"],
            # Everything published besides the YAML, for the personal-data scan.
            "listing": [
                *content["golden_tasks"],
                {"name": content["name"], "summary": content["summary"]},
                {"use_when": content["use_when"]},
            ],
            "observed_taint": taint,
            "parent": parent,
            "review": _review(info.name, content, taint, parent),
        }
        logger.info("Commons offer of %r prepared (%s…)", name, (digest or "")[:12])
        return _done(context, key, output, "propose")


class CommonsOfferRouteAction(TaskAction):
    """Route ``owner`` when ``tainted_by`` holds an observed or unknown sphere, else ``trusted``.

    The owner route is a human task no trust level or freeing skips; ``commons_offer_record``
    checks the taint again for an unattended approval.
    """

    description = "Choose who approves an offer: the owner (observed taint) or the trust gate."
    reversibility_hint = "always_reversible"

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        offer = context.process.properties.get("offer") or {}
        taint = offer.get("observed_taint")
        route = "trusted" if taint == [] else "owner"  # missing = owner (fail closed)
        output = {"route": route, "observed_taint": taint}
        return _done(context, task.properties.get("output_key", "offer_route"), output, route)


async def _journal_offer(context: ExecutionContext) -> tuple[dict[str, Any], dict[str, Any]]:
    """``(steps, offer)``: the step journal and the offer ``prepare`` wrote, per the journal."""
    steps = await completed_steps(context)
    event = steps.get(PREPARE_TASK)
    offer = event.changed.get(f"__task_output_{PREPARE_TASK}") if event is not None else None
    return steps, offer if isinstance(offer, dict) else {}


def _missing(steps: dict[str, Any], gates: dict[str, str]) -> str | None:
    for gate, route in gates.items():
        event = steps.get(gate)
        if event is None or event.next_route != route:
            return gate
    return None


class CommonsOfferRecordAction(TaskAction):
    """Record the offer decision: approved adds ``public`` to ``share_with``; routes ``approved``
    / ``declined``.

    ``auto: true`` (the trust gate proceeded) needs the journal to show prepare, the scan,
    ethics, the route and the gate, and no observed taint on the current version; otherwise
    ``approval_task`` must hold the owner's ``decision: publish``. Approval is void if the
    workflow changed since it was prepared. Each decision is a ``share`` journal record for
    sphere ``public``.
    """

    description = "Record an offer approval (adds 'public' to share_with) or a decline."
    reversibility_hint = "context_dependent"  # writes share_with and the journal

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        from zebra_agent.commons.offer import PUBLIC_SPHERE
        from zebra_agent.commons.sync import APPROVED, DECLINED, record_share

        key = task.properties.get("output_key", "offer_decision")
        if not is_offer_workflow(context.process_definition):
            logger.warning("commons_offer_record refused outside the Commons Offer workflow")
            return TaskResult.fail("commons_offer_record runs only in the Commons Offer workflow")
        publisher, library = _services(context)
        steps, offer = await _journal_offer(context)
        name, digest = offer.get("name", ""), offer.get("content_sha256")
        # The task definition, not the instance: what the shipped workflow says.
        props = context.task_definition.properties
        auto = props.get("auto") is True
        approval = props.get("approval_task")
        reason: str | None
        if auto:
            missing = _missing(steps, _GATES_UNATTENDED)
            approved, reason = missing is None, f"no record that {missing} passed"
            if approved:
                reason = "approved by earned sharing autonomy"
        else:
            answer = human_answer(steps, approval) if approval else None
            approved = bool(answer) and answer.get("decision") == DECISION_PUBLISH
            note = (answer or {}).get("note") or ""
            reason = note or ("approved by the owner" if approved else "the owner kept it private")
            missing = _missing(steps, _GATES_TO_OWNER)
            if approved and missing:
                approved, reason = False, f"no record that {missing} passed"
        if publisher is None or library is None:
            approved, reason = False, "no publisher or library — failing closed"
        elif approved and auto:
            info = await library.get_workflow_info(name)
            taint = publisher.observed_taint((info.commons if info else None) or {})
            if taint or offer.get("observed_taint") != []:
                approved, reason = False, "observed taint always needs the owner's approval"
        if approved and not library.approve_share(name, PUBLIC_SPHERE, digest):
            approved, reason = False, "the workflow changed since the offer was prepared"
        if library is not None:
            status = APPROVED if approved else DECLINED
            record_share(library, name, digest, PUBLIC_SPHERE, status, reason=reason)
        output = {"approved": approved, "reason": reason, "name": name}
        return _done(context, key, output, "approved" if approved else "declined")


class CommonsPublishAction(TaskAction):
    """Publish the approved ``OFFER``; routes ``published`` / ``not_published``.

    Only in the shipped *Commons Offer*, after the journal shows prepare, the scan and an
    approval record. Checks again, on the current version: the preconditions, the hash it was
    prepared for, ``public`` in ``share_with``, the Commons not stopped. Then signs and
    publishes through the ``CommonsPublisher`` (hard filter, certs first, canonical relay,
    mirrors, receipt, local mirror) and records ``sent`` for sphere ``public``.
    """

    description = "Sign and publish an approved OFFER to the public Commons relays."
    reversibility_hint = "always_irreversible"  # public, cannot be taken back

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        from zebra_agent.commons.offer import PUBLIC_SPHERE, OfferRefused, publish_refusal
        from zebra_agent.commons.sync import BLOCKED, SENT, record_share

        key = task.properties.get("output_key", "offer_published")
        if not is_offer_workflow(context.process_definition):
            logger.warning("commons_publish refused outside the Commons Offer workflow")
            return TaskResult.fail("commons_publish runs only in the Commons Offer workflow")
        publisher, library = _services(context)
        steps, offer = await _journal_offer(context)
        name, digest = offer.get("name", ""), offer.get("content_sha256")

        def refuse(reason: str) -> TaskResult:
            logger.warning("Commons offer of %r not published: %s", name, reason)
            if library is not None:
                record_share(library, name, digest, PUBLIC_SPHERE, BLOCKED, reason=reason)
            return _done(context, key, {"published": False, "reason": reason}, "not_published")

        if publisher is None or library is None:
            return refuse("no publisher or library — failing closed")
        missing = _missing(steps, _GATES_TO_OWNER)
        approvals = [steps.get(t) for t in ("record_auto", "record_asked")]
        if missing or not any(e is not None and e.next_route == "approved" for e in approvals):
            return refuse(f"no record that {missing or 'an approval'} passed")
        stopped = await commons_stop_reason(context.extras)
        if stopped:
            return refuse(f"the Commons is stopped: {stopped}")
        info = await library.get_workflow_info(name)
        try:
            stats, _gym = await _runs_and_stats(library, context, name)
        except Exception as e:  # noqa: BLE001
            return refuse(f"could not read the run statistics: {e}")
        reason = publish_refusal(info, library, stats.total_runs if stats else 0, digest)
        if reason:
            return refuse(reason)
        content = offer.get("content")
        if not isinstance(content, dict) or content.get("yaml") != offer.get("yaml"):
            return refuse("no prepared offer content in the step journal")
        try:
            result = await publisher.publish_offer(content, info.commons or {})
        except OfferRefused as e:
            return refuse(str(e))
        except Exception as e:  # noqa: BLE001 - PublishRefused, RelayUnavailable, ...
            return refuse(f"the canonical relay did not take the offer: {str(e)[:300]}")
        record_share(
            library,
            name,
            digest,
            PUBLIC_SPHERE,
            SENT,
            reason="offered",
            event_id=result["event_id"],
        )
        return _done(context, key, {"published": True, **result}, "published")


class CommonsRecordOfferAction(TaskAction):
    """Record how an offer ended as ``commons_offer_result`` (published, refused, declined)."""

    description = "Record a Commons offer's outcome: published, or refused/declined with a reason."
    reversibility_hint = "always_reversible"  # writes only this run's result property
    inputs = [
        ParameterDef(name="status", type="string", description="Outcome", required=True),
        ParameterDef(name="stage", type="string", description="Gate that decided", required=True),
        ParameterDef(name="reason", type="string", description="Why", required=False),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        props = context.process.properties
        offer = props.get("offer") if isinstance(props.get("offer"), dict) else {}
        published = (
            props.get("offer_published") if isinstance(props.get("offer_published"), dict) else {}
        )
        reason = resolve_raw(context, task.properties.get("reason") or "")
        if not isinstance(reason, str) or not reason.strip() or "{{" in reason:
            reason = "no reason recorded"
        result = {
            "status": str(task.properties.get("status") or "refused"),
            "stage": str(task.properties.get("stage") or "unknown"),
            "reason": reason.strip()[:2000],
            "workflow": offer.get("name") or props.get("workflow_name"),
            "content_sha256": offer.get("content_sha256"),
            "event_id": published.get("event_id"),
            "receipt_seq": published.get("receipt_seq"),
        }
        context.set_process_property(RESULT_KEY, result)
        logger.info(
            "Commons offer %s at %s: %s", result["status"], result["stage"], result["reason"][:200]
        )
        return TaskResult.ok(output=result)
