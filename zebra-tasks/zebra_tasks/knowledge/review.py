"""ReviewKnowledgeAction — dream-cycle review of personal knowledge (F153).

Per user with workflow runs since the last dream cycle, an LLM compares the
user's active knowledge entries with those runs (goals, human-task answers,
continuation comments, outcomes, ratings) and proposes five kinds of action:

- ``new``: a fact that recurs in the runs but is not stored;
- ``update``: an entry the runs contradict or refine;
- ``stale``: an entry that looks out of date;
- ``merge``: near-duplicate entries;
- ``reinforce``: an entry the runs confirm.

Proposals are applied under fixed rules:

- ``source="agent"`` entries may be changed directly (value, confidence,
  ``last_verified``, soft delete for merged duplicates);
- ``source="human"`` entries are never changed — a conflicting value starts the
  *Resolve Knowledge Contradiction* workflow, and stale / duplicate human
  entries start *Knowledge Verification* for exactly those entries;
- new facts follow ``add_knowledge`` semantics (``source="agent"``, confidence
  below 1.0); a clash with an existing key is treated as an ``update``;
- nothing is hard-deleted; stale agent entries lose confidence so the weekly
  verification picks them up.

Every change is recorded in ``changes`` with the entry's state before and after,
so the review can be audited and undone (:func:`revert_knowledge_changes`).
Users with no runs in the window are never looked at, so they cost no LLM call.
"""

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from zebra.core.models import ProcessState, TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.llm.base import Message

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 7
AGENT_CONFIDENCE = 0.7  # confidence of a newly learned / updated agent fact
MAX_AGENT_CONFIDENCE = 0.9  # agent facts never reach 1.0 without a human
STALE_CONFIDENCE_CAP = 0.5  # below the weekly verification threshold (0.6)
REINFORCE_STEP = 0.1
CLIP = 300  # characters per run field shown to the LLM

CONTRADICTION_WORKFLOW = "Resolve Knowledge Contradiction"
VERIFICATION_WORKFLOW = "Knowledge Verification"

# Actions that change an entry directly (and can be reverted); the rest are proposals.
DIRECT_ACTIONS = ("added", "updated", "stale_flagged", "merged", "reinforced")
COUNT_KEYS = (
    "added",
    "updated",
    "stale_flagged",
    "merged",
    "reinforced",
    "contradictions_proposed",
    "verifications_proposed",
)

SYSTEM_PROMPT = """You maintain a personal knowledge base about one user of an AI agent.
You are given the user's stored knowledge entries and the workflow runs they did recently
(goals, their answers to questions, continuation comments, outcomes, ratings).

Propose changes so the knowledge stays current. Only use evidence from the runs; never invent
facts. Only store durable personal facts (preferences, facts about the user, relationships,
routines, skills, history) — not one-off task details. Be conservative: no change is fine.

Return ONLY a JSON object:
{
  "new": [{"category": "<one of CATEGORIES>", "key": "snake_case_key", "value": "...",
           "time_sensitive": false, "confidence": 0.7, "evidence": "why"}],
  "update": [{"entry_id": "...", "value": "new value", "evidence": "why"}],
  "stale": [{"entry_id": "...", "reason": "why it looks out of date"}],
  "merge": [{"keep_id": "...", "remove_ids": ["..."], "reason": "why they are duplicates"}],
  "reinforce": [{"entry_id": "...", "evidence": "run that confirms it"}]
}

- new: facts that recur across the runs but are not stored yet.
- update: entries the runs contradict or refine (e.g. a changed employer or routine).
- stale: entries that look out of date and that the runs neither touch nor confirm
  (time-sensitive entries especially).
- merge: duplicate or near-duplicate entries; keep the best one.
- reinforce: entries the runs confirm.
Use entry ids exactly as given. Each entry id may appear in at most one list."""


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _clip(value: Any, limit: int = CLIP) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + "…"


def normalize_key(key: str) -> str:
    """Normalise a knowledge key to lower snake_case."""
    return re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")


def _snapshot(entry: Any) -> dict[str, Any]:
    return {
        "value": entry.value,
        "confidence": entry.confidence,
        "last_verified": _iso(entry.last_verified),
        "deleted_at": _iso(entry.deleted_at),
    }


def _empty_output(cutoff: datetime | None = None) -> dict[str, Any]:
    return {
        "cutoff": _iso(cutoff),
        "users_reviewed": 0,
        "runs_reviewed": 0,
        "counts": dict.fromkeys(COUNT_KEYS, 0),
        "examples": {k: [] for k in COUNT_KEYS},
        "changes": [],
        "errors": [],
    }


def _parse_json(content: str) -> dict[str, Any]:
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
    if match:
        content = match.group(1)
    else:
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end > start:
            content = content[start : end + 1]
    data = json.loads(content)
    return data if isinstance(data, dict) else {}


def _get_provider(task: TaskInstance, context: ExecutionContext) -> Any:
    """Resolve the LLM provider the same way the other dream-cycle actions do."""
    from zebra_tasks.llm.providers.registry import get_provider

    provider_name = task.properties.get("provider") or context.process.properties.get(
        "__llm_provider_name__"
    )
    model = task.properties.get("model") or context.process.properties.get("__llm_model__")
    if provider_name:
        return get_provider(provider_name, model)
    return context.process.properties.get("__llm_provider__")


def _track_cost(context: ExecutionContext, response: Any) -> None:
    from zebra_tasks.llm.pricing import calculate_cost

    usage = response.usage
    tokens = context.get_process_property("__total_tokens__", 0)
    context.set_process_property("__total_tokens__", tokens + usage.total_tokens)
    cost = calculate_cost(response.model, usage.input_tokens, usage.output_tokens)
    total = context.get_process_property("__total_cost__", 0.0)
    context.set_process_property("__total_cost__", total + cost)


async def last_dream_cycle_at(context: ExecutionContext) -> datetime | None:
    """Return when the previous completed run of this workflow started, if known."""
    try:
        processes = await context.store.list_processes(
            definition_id=context.process.definition_id, include_completed=True
        )
    except Exception as e:
        logger.warning("Knowledge review: could not list previous dream cycles: %s", e)
        return None
    starts = [
        p.created_at
        for p in processes
        if p.id != context.process.id and p.state == ProcessState.COMPLETE
    ]
    if not starts:
        return None
    latest = max(starts)
    return latest if latest.tzinfo else latest.replace(tzinfo=UTC)


async def revert_knowledge_changes(knowledge_store: Any, changes: list[dict[str, Any]]) -> int:
    """Undo the direct changes recorded by a knowledge review.

    Added entries are soft-deleted; updated, stale-flagged, reinforced and merged
    entries get their recorded ``before`` state back. Proposals (contradiction /
    verification workflows) changed nothing and are skipped. Best effort, one entry
    at a time in reverse order (not atomic); re-running it is harmless.

    Returns:
        Number of entries reverted.
    """
    reverted = 0
    for change in reversed(changes):
        entry_id = change.get("entry_id")
        action = change.get("action")
        if not entry_id or action not in DIRECT_ACTIONS:
            continue
        if action == "added":
            if await knowledge_store.soft_delete_entry(entry_id):
                reverted += 1
            continue
        entry = await knowledge_store.get_entry(entry_id)
        before = change.get("before") or {}
        if entry is None or not before:
            continue
        entry.value = before["value"]
        entry.confidence = before["confidence"]
        entry.last_verified = datetime.fromisoformat(before["last_verified"])
        deleted_at = before.get("deleted_at")
        entry.deleted_at = datetime.fromisoformat(deleted_at) if deleted_at else None
        entry.updated_at = datetime.now(UTC)
        await knowledge_store.update_entry(entry)
        reverted += 1
    return reverted


class ReviewKnowledgeAction(TaskAction):
    """Review each active user's personal knowledge against their recent runs (F153).

    Requires ``__metrics_store__`` and ``__knowledge_store__`` in ``context.extras``;
    ``__workflow_library__`` is used to find human tasks and to start the
    contradiction / verification workflows. Degrades gracefully: a missing store,
    LLM error or unparseable reply is logged and reported in ``errors``; the task
    always succeeds so the dream cycle continues.

    Properties:
        lookback_days: Window used when no previous dream cycle is found (default 7)
        max_users: Users reviewed per cycle (default 20)
        max_runs_per_user: Most recent runs shown to the LLM per user (default 20)
        max_entries: Knowledge entries shown to the LLM per user (default 100)
        max_changes_per_user: Cap on new/update/stale/merge actions per user (default 10)
        provider / model: LLM override (default: the dream cycle's provider and model)
        output_key: Process property for the result (default "knowledge_review")
    """

    description = (
        "Dream-cycle review of personal knowledge against recent runs: add, update, "
        "flag stale, merge and reinforce entries; human entries only via proposals."
    )
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="lookback_days",
            type="int",
            description="Days to look back when no previous dream cycle is found",
            required=False,
            default=DEFAULT_LOOKBACK_DAYS,
        ),
        ParameterDef(
            name="max_users",
            type="int",
            description="Maximum users reviewed per cycle",
            required=False,
            default=20,
        ),
        ParameterDef(
            name="max_runs_per_user",
            type="int",
            description="Most recent runs shown to the LLM per user",
            required=False,
            default=20,
        ),
        ParameterDef(
            name="max_entries",
            type="int",
            description="Knowledge entries shown to the LLM per user",
            required=False,
            default=100,
        ),
        ParameterDef(
            name="max_changes_per_user",
            type="int",
            description="Cap on new/update/stale/merge actions applied per user",
            required=False,
            default=10,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key for the review result",
            required=False,
            default="knowledge_review",
        ),
    ]

    outputs = [
        ParameterDef(
            name="counts",
            type="dict",
            description="Counts per action: " + ", ".join(COUNT_KEYS),
            required=True,
        ),
        ParameterDef(
            name="examples",
            type="dict",
            description="Up to three human-readable examples per action",
            required=True,
        ),
        ParameterDef(
            name="changes",
            type="list[dict]",
            description="Audit trail: one record per change or proposal, with before/after",
            required=True,
        ),
        ParameterDef(
            name="users_reviewed", type="int", description="Users reviewed", required=True
        ),
        ParameterDef(
            name="errors", type="list[string]", description="Non-fatal errors", required=True
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        output_key = task.properties.get("output_key", "knowledge_review")
        result = await self._review(task, context)
        context.set_process_property(output_key, result)
        return TaskResult.ok(output=result)

    async def _review(self, task: TaskInstance, context: ExecutionContext) -> dict[str, Any]:
        metrics_store = context.extras.get("__metrics_store__")
        knowledge_store = context.extras.get("__knowledge_store__")
        if metrics_store is None or knowledge_store is None:
            logger.warning("Knowledge review: metrics or knowledge store missing — skipping")
            out = _empty_output()
            out["errors"].append("metrics or knowledge store unavailable")
            return out

        lookback = int(task.properties.get("lookback_days", DEFAULT_LOOKBACK_DAYS))
        cutoff = await last_dream_cycle_at(context) or datetime.now(UTC) - timedelta(days=lookback)
        out = _empty_output(cutoff)

        try:
            runs = list(await metrics_store.get_runs_since(cutoff))
        except Exception as e:
            logger.warning("Knowledge review: could not load runs: %s", e)
            out["errors"].append(f"could not load runs: {e}")
            return out

        by_user: dict[int, list[Any]] = {}
        for run in runs:
            if getattr(run, "user_id", None) is not None:
                by_user.setdefault(run.user_id, []).append(run)
        if not by_user:
            logger.info("Knowledge review: no user runs since %s", cutoff.isoformat())
            return out

        max_users = int(task.properties.get("max_users", 20))
        # Most active users first.
        users = sorted(by_user, key=lambda u: len(by_user[u]), reverse=True)[:max_users]
        for user_id in users:
            try:
                user_runs = by_user[user_id]
                await self._review_user(task, context, knowledge_store, user_id, user_runs, out)
                out["users_reviewed"] += 1
            except Exception as e:
                logger.warning("Knowledge review failed for user %s: %s", user_id, e)
                out["errors"].append(f"user {user_id}: {e}")
        logger.info("Knowledge review: %d users, counts=%s", out["users_reviewed"], out["counts"])
        return out

    # ------------------------------------------------------------------
    # Gather
    # ------------------------------------------------------------------

    async def _run_context(self, context: ExecutionContext, run: Any) -> dict[str, Any]:
        """Summarise one run for the LLM, including the user's human-task answers."""
        item: dict[str, Any] = {
            "run_id": run.id,
            "started_at": _iso(run.started_at),
            "workflow": run.workflow_name,
            "goal": _clip(run.goal),
            "success": bool(run.success),
            "rating": run.user_rating,
            "outcome": _clip(run.error if run.error else run.output),
        }
        if run.continuation_comment:
            item["continuation_comment"] = _clip(run.continuation_comment)
        answers = await self._human_answers(context, run)
        if answers:
            item["human_answers"] = answers
        return item

    async def _human_answers(self, context: ExecutionContext, run: Any) -> list[dict[str, str]]:
        library = context.extras.get("__workflow_library__")
        metrics_store = context.extras.get("__metrics_store__")
        if library is None:
            return []
        try:
            definition = library.get_workflow(run.workflow_name)
        except Exception:
            return []
        human_ids = {tid for tid, t in definition.tasks.items() if not t.auto}
        if not human_ids:
            return []
        try:
            executions = await metrics_store.get_task_executions(run.id)
        except Exception as e:
            logger.warning("Knowledge review: no task executions for run %s: %s", run.id, e)
            return []
        return [
            {"task": e.task_name, "answer": _clip(e.output)}
            for e in executions
            if e.task_definition_id in human_ids and e.output is not None
        ]

    # ------------------------------------------------------------------
    # Analyse + act, per user
    # ------------------------------------------------------------------

    async def _review_user(
        self,
        task: TaskInstance,
        context: ExecutionContext,
        store: Any,
        user_id: int,
        runs: list[Any],
        out: dict[str, Any],
    ) -> None:
        max_runs = int(task.properties.get("max_runs_per_user", 20))
        max_entries = int(task.properties.get("max_entries", 100))
        runs = sorted(runs, key=lambda r: r.started_at, reverse=True)[:max_runs]
        entries = (await store.get_entries(user_id))[:max_entries]
        run_items = [await self._run_context(context, r) for r in runs]
        out["runs_reviewed"] += len(run_items)

        proposals = await self._propose(task, context, entries, run_items)
        if proposals is None:
            out["errors"].append(f"user {user_id}: LLM reply unusable")
            return

        applier = _Applier(context, store, user_id, {e.id: e for e in entries}, out)
        await applier.apply(proposals, int(task.properties.get("max_changes_per_user", 10)))

    async def _propose(
        self,
        task: TaskInstance,
        context: ExecutionContext,
        entries: list[Any],
        run_items: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        from zebra_agent.knowledge import KNOWLEDGE_CATEGORIES

        provider = _get_provider(task, context)
        if provider is None:
            logger.warning("Knowledge review: no LLM provider")
            return None
        entry_items = [
            {
                "id": e.id,
                "category": e.category,
                "key": e.key,
                "value": e.value,
                "source": e.source,
                "confidence": round(e.confidence, 2),
                "last_verified": _iso(e.last_verified),
                "time_sensitive": e.time_sensitive,
            }
            for e in entries
        ]
        prompt = (
            f"Today: {datetime.now(UTC).date().isoformat()}\n"
            f"CATEGORIES: {', '.join(KNOWLEDGE_CATEGORIES)}\n\n"
            f"## Stored knowledge entries\n{json.dumps(entry_items, indent=1)}\n\n"
            f"## Recent runs (newest first)\n{json.dumps(run_items, indent=1)}"
        )
        try:
            response = await provider.complete(
                messages=[Message.system(SYSTEM_PROMPT), Message.user(prompt)],
                temperature=0.2,
                max_tokens=2000,
            )
            _track_cost(context, response)
            return _parse_json(response.content or "")
        except Exception as e:
            logger.warning("Knowledge review: LLM call or parse failed: %s", e)
            return None


class _Applier:
    """Apply one user's proposals under the source rules and record the audit trail."""

    def __init__(
        self,
        context: ExecutionContext,
        store: Any,
        user_id: int,
        entries: dict[str, Any],
        out: dict[str, Any],
    ) -> None:
        self.context = context
        self.store = store
        self.user_id = user_id
        self.entries = entries
        self.out = out
        self.touched: set[str] = set()
        self.verify: list[tuple[Any, str]] = []

    def _record(
        self,
        action: str,
        entry: Any,
        before: dict | None,
        reason: str,
        example: str,
        **extra: Any,
    ) -> None:
        self.out["counts"][action] += 1
        if len(self.out["examples"][action]) < 3:
            self.out["examples"][action].append(example)
        self.out["changes"].append(
            {
                "action": action,
                "user_id": self.user_id,
                "entry_id": entry.id if entry is not None else None,
                "category": entry.category if entry is not None else None,
                "key": entry.key if entry is not None else None,
                "source": entry.source if entry is not None else None,
                "before": before,
                "after": _snapshot(entry) if action in DIRECT_ACTIONS else None,
                "reason": _clip(reason, 200),
                "at": datetime.now(UTC).isoformat(),
                **extra,
            }
        )

    def _entry(self, entry_id: Any) -> Any:
        entry = self.entries.get(str(entry_id)) if entry_id else None
        if entry is None or entry.id in self.touched:
            return None
        return entry

    async def apply(self, proposals: dict[str, Any], max_changes: int) -> None:
        def items(kind: str) -> list[dict]:
            value = proposals.get(kind) or []
            return [p for p in value if isinstance(p, dict)] if isinstance(value, list) else []

        budget = max_changes
        for p in items("update"):
            if budget <= 0:
                break
            entry = self._entry(p.get("entry_id"))
            if entry is not None and p.get("value"):
                budget -= await self._update(entry, str(p["value"]), str(p.get("evidence", "")))
        for p in items("merge"):
            if budget <= 0:
                break
            budget -= await self._merge(p)
        for p in items("stale"):
            if budget <= 0:
                break
            entry = self._entry(p.get("entry_id"))
            if entry is not None:
                budget -= await self._stale(entry, str(p.get("reason", "")))
        for p in items("reinforce"):
            entry = self._entry(p.get("entry_id"))
            if entry is not None:
                await self._reinforce(entry, str(p.get("evidence", "")))
        for p in items("new"):
            if budget <= 0:
                break
            budget -= await self._new(p)
        await self._propose_verification()

    async def _update(self, entry: Any, value: str, evidence: str) -> int:
        self.touched.add(entry.id)
        if value == entry.value:
            await self._reinforce(entry, evidence)
            return 0
        if entry.source != "agent":
            await self._propose_contradiction(entry, value, evidence)
            return 1
        before = _snapshot(entry)
        now = datetime.now(UTC)
        entry.value = value
        entry.confidence = AGENT_CONFIDENCE
        entry.last_verified = now
        entry.updated_at = now
        await self.store.update_entry(entry)
        self._record(
            "updated", entry, before, evidence, f"{entry.key}: {before['value']!r} → {value!r}"
        )
        return 1

    async def _stale(self, entry: Any, reason: str) -> int:
        from zebra_agent.knowledge import CONFIDENCE_DECAY_FLOOR

        self.touched.add(entry.id)
        if entry.source != "agent":
            self.verify.append((entry, reason))
            return 1
        before = _snapshot(entry)
        new_conf = min(entry.confidence * 0.5, STALE_CONFIDENCE_CAP)
        entry.confidence = max(CONFIDENCE_DECAY_FLOOR, new_conf)
        entry.updated_at = datetime.now(UTC)
        await self.store.update_entry(entry)
        self._record(
            "stale_flagged",
            entry,
            before,
            reason,
            f"{entry.key} (confidence {before['confidence']:.2f} → {entry.confidence:.2f})",
        )
        return 1

    async def _reinforce(self, entry: Any, evidence: str) -> None:
        self.touched.add(entry.id)
        if entry.source != "agent":
            return  # human entries are only changed by the human
        before = _snapshot(entry)
        now = datetime.now(UTC)
        entry.last_verified = now
        entry.confidence = min(MAX_AGENT_CONFIDENCE, entry.confidence + REINFORCE_STEP)
        entry.updated_at = now
        await self.store.update_entry(entry)
        self._record("reinforced", entry, before, evidence, entry.key)

    async def _merge(self, proposal: dict[str, Any]) -> int:
        keep = self._entry(proposal.get("keep_id"))
        remove_ids = proposal.get("remove_ids") or []
        if keep is None or not isinstance(remove_ids, list):
            return 0
        reason = str(proposal.get("reason", ""))
        self.touched.add(keep.id)
        applied = 0
        for rid in remove_ids:
            dup = self._entry(rid)
            if dup is None or dup.id == keep.id:
                continue
            self.touched.add(dup.id)
            if dup.source != "agent":
                self.verify.append((dup, f"possible duplicate of {keep.key}: {reason}"))
                continue
            before = _snapshot(dup)
            await self.store.soft_delete_entry(dup.id)
            refreshed = await self.store.get_entry(dup.id)
            self._record(
                "merged",
                refreshed or dup,
                before,
                reason,
                f"{dup.key} → {keep.key}",
                merged_into=keep.id,
            )
            applied += 1
        return 1 if applied else 0

    async def _new(self, proposal: dict[str, Any]) -> int:
        from zebra_agent.knowledge import KNOWLEDGE_CATEGORIES, KnowledgeEntry

        category = str(proposal.get("category", "")).strip().lower()
        key = normalize_key(proposal.get("key", ""))
        value = str(proposal.get("value", "")).strip()
        if category not in KNOWLEDGE_CATEGORIES or not key or not value:
            return 0
        evidence = str(proposal.get("evidence", ""))
        existing = await self.store.find_contradicting_entry(self.user_id, category, key)
        if existing is not None:
            # add_knowledge semantics: same value refreshes, a different value is a conflict.
            if existing.id in self.touched:
                return 0
            self.entries.setdefault(existing.id, existing)
            return await self._update(existing, value, evidence)
        try:
            confidence = float(proposal.get("confidence", AGENT_CONFIDENCE))
        except (TypeError, ValueError):
            confidence = AGENT_CONFIDENCE
        confidence = min(max(confidence, 0.1), MAX_AGENT_CONFIDENCE)
        entry = KnowledgeEntry.create(
            user_id=self.user_id,
            category=category,
            key=key,
            value=value,
            source="agent",
            confidence=confidence,
            time_sensitive=bool(proposal.get("time_sensitive", False)),
        )
        await self.store.add_entry(entry)
        self.touched.add(entry.id)
        self._record("added", entry, None, evidence, f"{key}: {value!r}")
        return 1

    # ------------------------------------------------------------------
    # Proposals for human entries
    # ------------------------------------------------------------------

    async def _pending(self, workflow: str) -> list[dict[str, Any]]:
        """Properties of unfinished processes of *workflow* (to avoid duplicate prompts)."""
        library = self.context.extras.get("__workflow_library__")
        try:
            definition = library.get_workflow(workflow)
            processes = await self.context.store.list_processes(definition_id=definition.id)
        except Exception:
            return []
        return [p.properties for p in processes]

    async def _start(self, workflow: str, properties: dict[str, Any]) -> str | None:
        library = self.context.extras.get("__workflow_library__")
        if library is None:
            logger.warning("Knowledge review: no workflow library — cannot start %s", workflow)
            return None
        definition = library.get_workflow(workflow)
        process = await self.context.engine.create_process(definition, properties=properties)
        await self.context.engine.start_process(process.id)
        return process.id

    async def _propose_contradiction(self, entry: Any, value: str, evidence: str) -> None:
        for props in await self._pending(CONTRADICTION_WORKFLOW):
            if props.get("entry_id") == entry.id and props.get("proposed_value") == value:
                return  # already waiting for the user
        try:
            process_id = await self._start(
                CONTRADICTION_WORKFLOW,
                {
                    "__user_id__": self.user_id,
                    "entry_id": entry.id,
                    "category": entry.category,
                    "key": entry.key,
                    "existing_value": entry.value,
                    "proposed_value": value,
                    "review_reason": _clip(evidence, 200),
                    "__knowledge_review__": True,
                },
            )
        except Exception as e:
            self.out["errors"].append(f"contradiction for {entry.key}: {e}")
            return
        if process_id is None:
            return
        self._record(
            "contradictions_proposed",
            entry,
            _snapshot(entry),
            evidence,
            f"{entry.key}: {entry.value!r} vs {value!r}",
            proposed_value=value,
            process_id=process_id,
        )

    async def _propose_verification(self) -> None:
        if not self.verify:
            return
        pending: set[str] = set()
        for props in await self._pending(VERIFICATION_WORKFLOW):
            ids = props.get("review_entry_ids")
            if isinstance(ids, list):
                pending.update(str(i) for i in ids)
        todo = [(e, r) for e, r in self.verify if e.id not in pending]
        if not todo:
            return
        try:
            process_id = await self._start(
                VERIFICATION_WORKFLOW,
                {
                    "__user_id__": self.user_id,
                    "review_entry_ids": [e.id for e, _ in todo],
                    "review_reason": "; ".join(f"{e.key}: {_clip(r, 100)}" for e, r in todo),
                    "__knowledge_review__": True,
                },
            )
        except Exception as e:
            self.out["errors"].append(f"verification proposal: {e}")
            return
        if process_id is None:
            return
        for entry, reason in todo:
            self._record(
                "verifications_proposed",
                entry,
                _snapshot(entry),
                reason,
                entry.key,
                process_id=process_id,
            )
