## Why

The personal knowledge store (#31/#32) is filled only by hand on `/knowledge/`. `add_knowledge` and its contradiction detection exist, but no workflow calls them, so prod has 0 entries and `consult_knowledge` has nothing to read. Issue #152.

## What Changes

- **New `extract_knowledge` action** (`zebra_tasks/knowledge/extract.py`).
  - A haiku call pulls `{category, key, value, time_sensitive, confidence}` candidates from the goal, the user's human-task answers, the continuation comment and the result.
  - It does not write anything, so other workflows (e.g. a dream-cycle review) can reuse it.
  - Guardrails:
    - skips with no LLM call when there is no user or no user-authored text;
    - categories must be in `KNOWLEDGE_CATEGORIES`;
    - keys are normalised to snake_case, and existing keys are offered to the LLM for reuse;
    - credential- or card-like values are always dropped;
    - special-category data (`sensitive`) is dropped unless the user opts in (`allow_sensitive` / `ZEBRA_KNOWLEDGE_ALLOW_SENSITIVE`);
    - a minimum confidence and a per-run cap apply.
- **New `store_learned_knowledge` action** (`zebra_tasks/knowledge/store_learned.py`).
  - Stores each candidate through `store_knowledge_entry`, the shared core of `add_knowledge`, as `source="agent"` with confidence capped at 0.5. That is below the 0.6 weekly-verification threshold, so the user is asked to verify.
  - A conflicting value is never written. It starts a *Resolve Knowledge Contradiction* process instead, and an identical pending conflict is not started twice.
- **Agent main loop v14:** `record_ethics_review → extract_knowledge → (has_candidates) store_learned_knowledge → report_outcome`. A `no_candidates` result goes straight to `report_outcome`.
- **`execute_goal_workflow`:** its result gains `user_inputs`, the child's human-task answers keyed by task name, without read-only fields.
- **`add_knowledge`:** gains an optional `confidence`. When a same-value refresh is given an explicit agent confidence, it keeps the higher confidence instead of jumping to 1.0.
- **`apply_resolution`:** `use_new` marks the entry `source="human"`.
- **Web `/knowledge/`:**
  - shows an `agent` badge and highlights confidence below 1;
  - adds a **Confirm** button (POST `/knowledge/<id>/confirm/` sets confidence 1.0 and source human);
  - hides soft-deleted entries.

## Capabilities

### New Capabilities
- `knowledge-learning`: the agent learns personal knowledge from goal runs.

### Modified Capabilities
<!-- none: knowledge-lifecycle behaviour is unchanged for existing callers -->

## Impact

- `zebra-tasks/zebra_tasks/knowledge/{extract,store_learned,add,apply_resolution}.py`, `agent/execute_workflow.py`, `pyproject.toml` (2 entry points)
- `zebra-agent/workflows/agent_main_loop.yaml` (v14)
- `zebra-agent-web/zebra_agent_web/api/web_views.py`, `urls.py`, `templates/pages/knowledge_list.html`
- No migrations. Depends on #151 (`__user_id__` on API goals) for API-submitted goals to learn anything.
