"""The dream cycle's Commons step (#235, S8): propose offers and imports, ask for ``sharing``.

``commons_dream`` runs near the end of ``dream_cycle.yaml``. It only *proposes*: every offer goes
through the *Commons Offer* workflow (the public suggest-and-approve step, with its scans, ethics
gate and the ``sharing`` trust gate or the owner) and every import through *Commons Import* (judge,
scans, ethics, gym, trust gate or owner, supervised adoption). Trades are out of scope while the
reputation market is parked (#234).

- **Off by default:** without a Commons publisher (``ZEBRA_COMMONS_RELAYS`` unset) or with
  ``COMMONS_DREAM_ENABLED`` false the step records ``status: off`` and does nothing else; with
  the Commons stopped (off or kill switch) ``status: stopped``.
- **Offers:** learnt workflows with enough runs and good stats that pass ``offer_refusal``,
  capped per cycle (``MAX_OFFERS_PER_CYCLE``).
- **Imports:** capability gaps (the creator wrote a workflow because the selector found none;
  continuations that reported ``new_workflow``) matched by keyword overlap against ``seen``
  offers whose import score clears ``IMPORT_SCORE_THRESHOLD``, capped per cycle
  (``MAX_IMPORTS_PER_CYCLE``) and by a daily budget (``DAILY_IMPORT_BUDGET_USD``) read from the
  spend ledger. Offer text never reaches an LLM here.
- **Sharing promotion:** after enough unchanged owner approvals of sharing proposals, a pending
  ``sharing`` suggestion via ``queue_promotion`` (REQ-TRUST-004); it never sets a level.

The step never fails the cycle: anything unexpected becomes ``status: error`` in its report.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from zebra.core.models import ProcessState, TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.commons.supervised import commons_stop_reason
from zebra_tasks.knowledge.extract import resolve_raw

logger = logging.getLogger(__name__)

PUBLISHER_KEY = "__commons_publisher__"
EXCHANGE_KEY = "__commons_exchange__"
LIBRARY_KEY = "__workflow_library__"
METRICS_KEY = "__metrics_store__"
TRUST_KEY = "__trust_store__"
OFFER_WORKFLOW = "Commons Offer"
IMPORT_WORKFLOW = "Commons Import"
#: Marks a *Commons Import* the dream cycle started (its spend counts against the budget).
DREAM_IMPORT_KEY = "__commons_dream_import__"
DREAM_OFFER_KEY = "__commons_dream_offer__"
SHARING = "sharing"
#: Keywords a gap and an offer must share to match.
MIN_SHARED_WORDS = 2
MAX_SKIPPED = 20
#: Share-record reasons that are the owner's plain approval (no note: nothing changed).
OWNER_PLAIN_APPROVALS = frozenset({"", "approved by the owner"})
AUTONOMY_APPROVAL = "approved by earned sharing autonomy"
NEXT_LEVEL = {"SUPERVISED": "SEMI_AUTONOMOUS", "SEMI_AUTONOMOUS": "AUTONOMOUS"}

# name: (env var, default)
SETTINGS: dict[str, tuple[str, Any]] = {
    "enabled": ("ZEBRA_COMMONS_DREAM_ENABLED", True),
    "max_offers": ("ZEBRA_COMMONS_MAX_OFFERS_PER_CYCLE", 1),
    "max_imports": ("ZEBRA_COMMONS_MAX_IMPORTS_PER_CYCLE", 1),
    "daily_import_budget": ("ZEBRA_COMMONS_DAILY_IMPORT_BUDGET_USD", 0.5),
    "offer_min_success_rate": ("ZEBRA_COMMONS_OFFER_MIN_SUCCESS_RATE", 0.8),
    "offer_min_rating": ("ZEBRA_COMMONS_OFFER_MIN_RATING", 4.0),
    "promotion_approvals": ("ZEBRA_COMMONS_SHARING_PROMOTION_APPROVALS", 5),
    "lookback_days": ("ZEBRA_COMMONS_DREAM_LOOKBACK_DAYS", 7),
}

_background: set[asyncio.Task] = set()


def setting(task: TaskInstance, name: str) -> Any:
    """A setting: task property > ``ZEBRA_COMMONS_*`` env var > default."""
    env_var, default = SETTINGS[name]
    raw = task.properties.get(name)
    if raw is None:
        raw = os.environ.get(env_var)
    if raw is None or raw == "":
        return default
    if isinstance(default, bool):
        return raw if isinstance(raw, bool) else str(raw).strip().lower() in ("1", "true", "yes")
    try:
        return type(default)(raw)
    except (TypeError, ValueError):
        logger.warning("Commons dream: bad %s=%r, using %r", env_var, raw, default)
        return default


async def wait_for_imports(timeout: float | None = None) -> bool:
    """Wait for the imports this step started in the background; True when none is left.

    Never cancels them: on *timeout* they keep running (``asyncio.wait``, not ``gather``).
    """
    loop = asyncio.get_running_loop()
    deadline = None if timeout is None else loop.time() + timeout
    while _background:
        left = None if deadline is None else deadline - loop.time()
        if left is not None and left <= 0:
            return False
        await asyncio.wait(list(_background), timeout=left)
    return True


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", (text or "").lower()))


def match_overlap(gap: str, offer_text: str) -> int:
    """Keywords of *gap* (the memory search's split) that *offer_text* also has."""
    from zebra_agent.storage.interfaces import search_keywords

    if not (gap or "").strip():
        return 0
    return len(set(search_keywords(gap)) & _words(offer_text))


def _start_of_day(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_at(value: Any) -> datetime | None:
    try:
        at = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return at if at.tzinfo else at.replace(tzinfo=UTC)


class _Report:
    """What the step did, for the dream-cycle summary and ``/dreams/``."""

    def __init__(self) -> None:
        self.status = "ran"
        self.voice: list[str] = []
        self.offers_proposed: list[dict[str, Any]] = []
        self.imports_started: list[dict[str, Any]] = []
        self.skipped: list[dict[str, Any]] = []
        self.budget: dict[str, Any] = {}
        self.promotion: dict[str, Any] | None = None
        self.errors: list[str] = []

    def skip(self, kind: str, name: str, reason: str) -> None:
        if len(self.skipped) < MAX_SKIPPED:
            self.skipped.append({"kind": kind, "name": name, "reason": reason})

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "voice": self.voice,
            "voice_text": " ".join(self.voice),
            "offers_proposed": self.offers_proposed,
            "imports_started": self.imports_started,
            "skipped": self.skipped,
            "budget": self.budget,
            "promotion": self.promotion,
            "errors": self.errors,
        }


class CommonsDreamAction(TaskAction):
    """Propose Commons offers and imports from the dream cycle, and ask for ``sharing``.

    Output (``output_key``, default ``commons``): ``{status (off / stopped / ran / error),
    voice, voice_text, offers_proposed, imports_started, skipped, budget, promotion, errors}``.
    Never fails.
    """

    description = (
        "Dream-cycle Commons step: propose offers of good learnt workflows and imports of "
        "trusted offers for capability gaps through their gated workflows; ask for sharing "
        "autonomy. Off without Commons relays."
    )
    # Starts the gated offer / import workflows, journals proposals, queues a suggestion.
    reversibility_hint = "context_dependent"
    inputs = [
        ParameterDef(
            name="capability_gaps",
            type="list",
            description="Continuation capability gaps from the metrics analysis",
            required=False,
        ),
        ParameterDef(name="output_key", type="string", description="Output key", required=False),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        key = task.properties.get("output_key", "commons")
        report = _Report()
        try:
            await self._run(task, context, report)
        except Exception as e:  # noqa: BLE001 - the dream cycle never fails here
            logger.exception("Commons dream step failed")
            report.status = "error"
            report.errors.append(str(e)[:300])
            report.voice.append(f"Something went wrong in the Commons step ({str(e)[:120]}).")
        output = report.to_dict()
        context.set_process_property(key, output)
        return TaskResult.ok(output=output)

    async def _run(self, task: TaskInstance, context: ExecutionContext, report: _Report) -> None:
        extras = context.extras
        publisher = extras.get(PUBLISHER_KEY)
        library = extras.get(LIBRARY_KEY)
        if not setting(task, "enabled"):
            report.status = "off"
            report.voice.append(
                "Commons proposals are switched off (COMMONS_DREAM_ENABLED), so I left the "
                "Commons alone."
            )
            return
        if publisher is None or library is None:
            report.status = "off"
            report.voice.append(
                "Commons off: no public relays are set on this device, so I didn't offer or "
                "look for anything there."
            )
            return
        stopped = await commons_stop_reason(extras)
        if stopped:
            report.status = "stopped"
            report.voice.append(f"The Commons is stopped ({stopped}), so I left it alone.")
            return
        owner = await library.refresh_owner()
        metrics = getattr(library, "metrics", None) or extras.get(METRICS_KEY)
        for part in (self._offers, self._imports, self._promotion):
            try:
                await part(task, context, report, publisher, library, metrics, owner)
            except Exception as e:  # noqa: BLE001 - one part never stops the others
                logger.exception("Commons dream step: %s failed", part.__name__)
                report.errors.append(f"{part.__name__.strip('_')}: {str(e)[:300]}")

    # -- offers ----------------------------------------------------------------------------

    async def _offer_candidates(
        self, task: TaskInstance, context: ExecutionContext, report: _Report,
        publisher: Any, library: Any, metrics: Any,
    ) -> list[dict[str, Any]]:  # fmt: skip
        from zebra_agent.commons import commons_exportable
        from zebra_agent.commons.offer import MIN_RUNS_TO_OFFER, PUBLIC_SPHERE, offer_refusal
        from zebra_agent.commons.sync import DECIDED, latest_decision

        if metrics is None:
            report.skip("offer", "-", "no metrics store, so I can't judge any workflow")
            return []
        min_rate = setting(task, "offer_min_success_rate")
        min_rating = setting(task, "offer_min_rating")
        builtin = library.builtin_hashes()
        offered = await publisher.offered_hashes()
        open_offers = await self._open_offer_names(context, library)
        out = []
        names: dict[str, None] = {}
        for listed in await library.list_workflows():
            # Cheap filters on the listing first: resolving a name reads the library.
            block = listed.commons or {}
            if not commons_exportable(listed) or block.get("content_sha256") in builtin:
                continue  # system, other users' runs, unknown lineage, a shipped built-in
            names[listed.name] = None
        for name in names:
            stats = await metrics.get_stats(name)
            runs = stats.total_runs if stats else 0
            if runs < MIN_RUNS_TO_OFFER:
                continue  # too young to judge: not worth a line in the report
            info = await library.get_workflow_info(name)  # the current file of this name
            if info is None or not commons_exportable(info):
                continue
            block = info.commons or {}
            digest = block.get("content_sha256")
            if not digest or digest in builtin or block.get("origin_pubkey"):
                continue  # a shipped built-in or another Zebra's workflow: not mine to offer
            if stats.success_rate < min_rate:
                report.skip(
                    "offer", name, f"success rate {stats.success_rate:.0%} < {min_rate:.0%}"
                )
                continue
            if stats.avg_rating is not None and stats.avg_rating < min_rating:
                report.skip("offer", name, f"average rating {stats.avg_rating:.1f} < {min_rating}")
                continue
            reason = offer_refusal(info, library, runs)
            if reason:
                report.skip("offer", name, reason)
                continue
            if digest in offered:
                continue  # already public
            if name in open_offers:
                report.skip("offer", name, "an offer of it is already waiting for an answer")
                continue
            shared = PUBLIC_SPHERE in (block.get("share_with") or [])
            if not shared and latest_decision(library, digest, PUBLIC_SPHERE) in DECIDED:
                continue  # this version was already asked about
            out.append(
                {
                    "name": name,
                    "content_sha256": digest,
                    "kind": "publish" if shared else "suggest",
                    "runs": runs,
                    "success_rate": round(stats.success_rate, 3),
                    "avg_rating": stats.avg_rating,
                }
            )
        out.sort(key=lambda c: (c["success_rate"], c["avg_rating"] or 0, c["runs"]), reverse=True)
        return out

    async def _open_offer_names(self, context: ExecutionContext, library: Any) -> set[str]:
        definition = library.get_workflow(OFFER_WORKFLOW)
        processes = await context.engine.store.list_processes(definition_id=definition.id)
        return {
            str((p.properties or {}).get("workflow_name"))
            for p in processes
            if p.state in (ProcessState.CREATED, ProcessState.RUNNING, ProcessState.PAUSED)
        }

    async def _offers(
        self, task: TaskInstance, context: ExecutionContext, report: _Report,
        publisher: Any, library: Any, metrics: Any, owner: int | None,
    ) -> None:  # fmt: skip
        from zebra_agent.commons.offer import PUBLIC_SPHERE
        from zebra_agent.commons.sync import FAILED, PROPOSED, record_share

        candidates = await self._offer_candidates(
            task, context, report, publisher, library, metrics
        )
        cap = max(0, setting(task, "max_offers"))
        for candidate in candidates[cap:]:
            report.skip("offer", candidate["name"], f"over this cycle's cap of {cap} offer(s)")
        for candidate in candidates[:cap]:
            name = candidate["name"]
            if candidate["kind"] == "suggest":  # before the run, which records the decision
                record_share(
                    library,
                    name,
                    candidate["content_sha256"],
                    PUBLIC_SPHERE,
                    PROPOSED,
                    reason="dream cycle",
                )
            properties: dict[str, Any] = {
                "workflow_name": name,
                "goal": f"Offer {name} to the public Commons",
                DREAM_OFFER_KEY: True,
            }
            if owner is not None:
                properties["__user_id__"] = owner
            try:
                process_id, state, result = await self._start_inline(
                    context, library, OFFER_WORKFLOW, properties
                )
            except Exception as e:
                if candidate["kind"] == "suggest":  # not a decision: may be asked again
                    record_share(
                        library, name, candidate["content_sha256"], PUBLIC_SPHERE, FAILED,
                        reason=f"the offer could not start: {e}",
                    )  # fmt: skip
                raise
            entry = {**candidate, "process_id": process_id}
            status = (result or {}).get("status")
            if state == ProcessState.RUNNING:
                entry["outcome"] = "waiting"
                report.offers_proposed.append(entry)
                report.voice.append(self._offer_voice(candidate))
            elif status == "published":
                entry["outcome"] = "published"
                report.offers_proposed.append(entry)
                report.voice.append(
                    f"I offered {name} publicly: my earned sharing autonomy let its checks "
                    "approve it."
                )
            else:
                reason = (result or {}).get("reason") or f"the offer ended {state}"
                report.skip("offer", name, f"the offer stopped: {reason}"[:300])
                report.voice.append(f"I tried to offer {name}, but it stopped: {reason}"[:300])
        if not report.offers_proposed and not candidates:
            report.voice.append("None of my workflows is ready to offer yet.")

    @staticmethod
    def _offer_voice(c: dict[str, Any]) -> str:
        rating = f", rated {c['avg_rating']:.1f}" if c.get("avg_rating") is not None else ""
        record = f"{c['success_rate']:.0%} of {c['runs']} runs worked{rating}"
        if c["kind"] == "publish":
            return (
                f"You'd already agreed to share {c['name']} publicly ({record}), so I started "
                "publishing it; its checks run again first."
            )
        return f"I asked you whether to offer {c['name']} to the public Commons ({record})."

    async def _start_inline(
        self, context: ExecutionContext, library: Any, workflow: str, properties: dict[str, Any]
    ) -> tuple[str, ProcessState | None, dict[str, Any] | None]:
        from zebra_tasks.launch import create_library_process

        engine = context.engine
        process = await create_library_process(
            engine, library.get_workflow(workflow), entry="dream_cycle", properties=properties
        )
        await engine.start_process(process.id)
        current = await engine.store.load_process(process.id)
        props = (current.properties if current else None) or {}
        result = props.get("commons_offer_result")
        if current is not None and current.state == ProcessState.FAILED:
            result = {"status": "failed", "reason": props.get("__error__") or "it failed"}
        return process.id, current.state if current else None, result

    # -- imports ---------------------------------------------------------------------------

    async def gaps(
        self, task: TaskInstance, context: ExecutionContext, library: Any
    ) -> list[dict[str, str]]:
        """``[{source, text}]``: creator-written workflows in the window, ``new_workflow``
        continuations."""
        days = setting(task, "lookback_days")
        since = datetime.now(UTC) - timedelta(days=days)
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for record in library.journal.read():
            if record.get("event") != "saved" or record.get("writer") != "creator":
                continue
            at = _parse_at(record.get("at"))
            name = str(record.get("name") or "")
            if not name or name in seen or at is None or at < since:
                continue
            seen.add(name)
            info = await library.get_workflow_info(name)
            text = " ".join(
                s for s in (name, info.description if info else "", info.use_when if info else "")
                if s
            )  # fmt: skip
            out.append({"source": "selector", "label": name, "text": text})
        raw = resolve_raw(context, task.properties.get("capability_gaps"))
        for gap in raw if isinstance(raw, list) else []:
            if not isinstance(gap, dict):
                continue
            text = " ".join(
                str(gap.get(k) or "") for k in ("comment", "rationale", "continuation_workflow")
            ).strip()
            if text:
                label = str(gap.get("comment") or gap.get("continuation_workflow") or "")[:80]
                out.append({"source": "continuation", "label": label, "text": text})
        return out

    async def _imports(
        self, task: TaskInstance, context: ExecutionContext, report: _Report,
        publisher: Any, library: Any, metrics: Any, owner: int | None,
    ) -> None:  # fmt: skip
        from zebra_agent.commons.exchange import attestation_summary, empty_summary
        from zebra_agent.commons.kinds import ATTEST_KIND
        from zebra_agent.commons.offers import SEEN
        from zebra_agent.commons.trust import IMPORT_SCORE_THRESHOLD
        from zebra_agent.commons.web_of_trust import offer_score

        exchange = context.extras.get(EXCHANGE_KEY)
        limit = float(setting(task, "daily_import_budget"))
        report.budget = {"limit": limit, "spent": 0.0, "remaining": limit}
        if exchange is None:
            report.skip("import", "-", "no Commons exchange, so I see no offers")
            return
        gaps = await self.gaps(task, context, library)
        if not gaps:
            report.voice.append("I found no capability gaps to look for in the Commons.")
            return
        offers = [o for o in await exchange.offers.list() if o.status == SEEN]
        if not offers:
            report.voice.append(
                f"I had {len(gaps)} capability gap(s), but I haven't seen any offers to try."
            )
            return
        attests = attestation_summary(
            [m.event for m in await exchange.mirror.events(kind=ATTEST_KIND)]
        )
        trust = await exchange.trust.trust_map() if exchange.trust is not None else {}
        candidates = []
        for offer in offers:
            text = f"{offer.name} {offer.summary} {offer.use_when}"
            best = max(gaps, key=lambda g: match_overlap(g["text"], text))
            overlap = match_overlap(best["text"], text)
            if overlap < MIN_SHARED_WORDS:
                continue
            summary = attests.get(offer.content_sha256, empty_summary())
            score = offer_score(
                offer.publisher_pubkey,
                [(i["zebra_pubkey"], i["label"]) for i in summary["items"]],
                trust,
                exchange.zebra_pubkey,
            )
            if not score["clears"]:
                report.skip(
                    "import",
                    offer.name,
                    f"import score {score['score']:.2f} < {IMPORT_SCORE_THRESHOLD:.2f}",
                )
                report.voice.append(
                    f"{offer.name} might fill the gap '{best['label']}', but I don't trust its "
                    f"publisher enough yet (score {score['score']:.2f} < "
                    f"{IMPORT_SCORE_THRESHOLD:.2f}), so I left it."
                )
                continue
            candidates.append((score["score"], overlap, offer, best))
        candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
        if not candidates:
            return
        spent = await self.spent_today(context, library, metrics)
        report.budget = {
            "limit": limit,
            "spent": round(spent, 4),
            "remaining": round(max(0.0, limit - spent), 4),
        }
        cap = max(0, setting(task, "max_imports"))
        started = 0
        for score, overlap, offer, gap in candidates:
            if started >= cap:
                report.skip("import", offer.name, f"over this cycle's cap of {cap} import(s)")
                continue
            if spent >= limit:
                report.skip("import", offer.name, "today's import budget is used")
                report.voice.append(
                    f"I've spent ${spent:.2f} of today's ${limit:.2f} import budget, so I "
                    f"won't try {offer.name} today."
                )
                continue
            process_id = await self._start_import(context, library, exchange, offer, owner)
            started += 1
            report.imports_started.append(
                {
                    "name": offer.name,
                    "content_sha256": offer.content_sha256,
                    "score": score,
                    "overlap": overlap,
                    "gap": gap["label"],
                    "gap_source": gap["source"],
                    "process_id": process_id,
                }
            )
            report.voice.append(
                f"I'm trying {offer.name} from another Zebra for the gap '{gap['label']}' "
                f"(import score {score:.2f}). It still has to pass every check, and you decide "
                "before I use it."
            )

    async def _start_import(
        self, context: ExecutionContext, library: Any, exchange: Any, offer: Any, owner: Any
    ) -> str:
        from zebra_tasks.launch import create_library_process

        engine = context.engine
        offer_event = await exchange.begin_import(offer.content_sha256)
        properties: dict[str, Any] = {
            "offer_event": offer_event,
            "goal": "Import a workflow offered on the Commons",
            DREAM_IMPORT_KEY: True,
        }
        if owner is not None:
            properties["__user_id__"] = owner
        try:
            process = await create_library_process(
                engine, library.get_workflow(IMPORT_WORKFLOW), entry="dream_cycle",
                properties=properties,
            )  # fmt: skip
        except Exception:
            await exchange.abandon_import(offer.content_sha256)
            raise

        async def run() -> None:
            try:
                await engine.start_process(process.id)
            except Exception:  # noqa: BLE001 - logged; the import's own steps record outcomes
                logger.exception("Commons dream: import %s failed to run", process.id)

        background = asyncio.create_task(run())
        _background.add(background)
        background.add_done_callback(_background.discard)
        logger.info("Commons dream: import %s of %s…", process.id, offer.content_sha256[:12])
        return process.id

    async def spent_today(self, context: ExecutionContext, library: Any, metrics: Any) -> float:
        """USD spent today (UTC) by dream-started imports: ledger sum over their process trees,
        else their ``__total_cost__``."""
        from zebra_agent.metrics import run_process_ids

        store = context.engine.store
        definition = library.get_workflow(IMPORT_WORKFLOW)
        since = _start_of_day(datetime.now(UTC))
        processes = await store.list_processes(definition_id=definition.id, include_completed=True)
        total = 0.0
        for p in processes:
            created = p.created_at if p.created_at.tzinfo else p.created_at.replace(tzinfo=UTC)
            if not (p.properties or {}).get(DREAM_IMPORT_KEY) or created < since:
                continue
            totals = None
            if metrics is not None:
                totals = await metrics.get_spend_for_processes(await run_process_ids(store, p.id))
            if totals is not None:
                total += float(totals[0] or 0.0)
            else:
                total += float((p.properties or {}).get("__total_cost__") or 0.0)
        return total

    # -- sharing promotion -----------------------------------------------------------------

    async def _promotion(
        self, task: TaskInstance, context: ExecutionContext, report: _Report,
        publisher: Any, library: Any, metrics: Any, owner: int | None,
    ) -> None:  # fmt: skip
        from zebra_tasks.agent.propose_trust_promotion import queue_promotion

        store = context.extras.get(TRUST_KEY)
        if store is None or owner is None:
            return
        level = str(await store.get_trust_level(owner, SHARING))
        target = NEXT_LEVEL.get(level)
        if target is None:
            return  # already autonomous (or unknown): nothing to ask for
        suggestions = [s for s in await store.list_suggestions(owner) if s.domain == SHARING]
        if any(s.status == "pending" for s in suggestions):
            return
        marks = [s.created_at for s in suggestions]
        marks += [c.changed_at for c in await store.list_trust_changes(owner, SHARING)]
        since = max(marks) if marks else None
        approvals, total = sharing_approvals(library, since)
        needed = max(1, setting(task, "promotion_approvals"))
        if approvals < needed:
            return
        evidence = (
            f"Since the last change to my sharing trust, you approved my last {approvals} "
            f"sharing proposals without changing anything ({total} decided in all, none "
            f"declined). I'd like to handle sharing at {target}: the personal-data scan, ethics "
            "review and observed-sphere approvals still apply."
        )
        suggestion = await queue_promotion(store, owner, SHARING, target, evidence)
        report.promotion = {
            "suggestion_id": suggestion.id,
            "from_level": level,
            "to_level": target,
            "approvals": approvals,
        }
        report.voice.append(
            f"You've approved my last {approvals} sharing proposals without changes, so I've "
            f"asked whether I may share with less supervision ({target}). You decide on /trust/."
        )


def sharing_approvals(library: Any, since: datetime | None) -> tuple[int, int]:
    """``(unchanged owner approvals in a row, owner decisions)`` among share records after
    *since*.

    An approval with no note counts; a decline or an approval with a note starts the count
    again; approvals by earned autonomy are not the owner's and do not count.
    """
    from zebra_agent.commons.sync import APPROVED, DECLINED, share_records

    run = decided = 0
    for record in share_records(library):
        at = _parse_at(record.get("at"))
        if since is not None and (at is None or at <= since):
            continue
        status = record.get("status")
        reason = record.get("reason") or ""
        if status == APPROVED and reason == AUTONOMY_APPROVAL:
            continue
        if status == APPROVED:
            decided += 1
            run = run + 1 if reason in OWNER_PLAIN_APPROVALS else 0
        elif status == DECLINED:
            decided += 1
            run = 0
    return run, decided
