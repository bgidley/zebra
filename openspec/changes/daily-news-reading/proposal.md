# Proposal

Closes #155

## Why

Zebra only learns when someone gives it a goal. The user wants it to keep up with the world on its
own: once a day, read the news on [news.kagi.com](https://news.kagi.com), pick 5 articles worth
learning about, read them, and remember what it learned. The knowledge store is meant to hold world
knowledge as well as facts about the user, so that is where the learnings go.

Two gaps stop a routine from doing this today. The scheduler can start a named workflow but cannot
queue a *goal*, so a routine run bypasses the budget daemon, the ethics gates, metrics and the
Activity view. And the knowledge store has only personal categories.

## What Changes

- **Routines can queue goals.** A `Routine` gains `goal`, `goal_priority` and `run_as`. When `goal`
  is set, `SchedulerLoop` calls an injected `queue_goal_fn` instead of creating a process. If the
  routine also names a `workflow`, the goal requests it. A routine never queues a second goal while
  its previous one is still `CREATED` or `RUNNING`. The web daemon wires `queue_goal_fn` to
  `api.goals.queue_goal`, running as `run_as` or the first active superuser.
- **Requested workflow.** `queue_goal` accepts `extra_properties`. `workflow_selector` honours a
  `requested_workflow` process property that names a library workflow: it routes `use_existing`
  without an LLM call.
- **Kagi News actions** (`zebra_tasks/web/kagi_news.py`):
  - `kagi_news_fetch` reads the public `kite.json` feed and returns compact story clusters.
  - `kagi_news_read` reads the picked stories with one Kagi Extract call and falls back to the
    cluster's own multi-source summary when extraction is unavailable.
- **Daily News Reading workflow.** Steps: consult knowledge → fetch → LLM picks exactly 5 stories →
  read → LLM writes a digest plus `world` knowledge candidates → `store_learned_knowledge`.
- **`world` knowledge category** with a 90-day decay half-life (Django choices migration).
  `store_learned_knowledge` gains `update_agent_entries`: a newer agent fact replaces an older agent
  fact in place. A conflict with a human entry still goes to *Resolve Knowledge Contradiction*.
- **`daily_news_reading` routine** (`fixtures/routines/daily_news_reading.yaml`) at 07:00 UTC.

## Capabilities

### New Capabilities
- `daily-news-reading`: a scheduled goal that reads the day's news and stores world knowledge.

## Impact

- `zebra-agent/zebra_agent/scheduler/{routine.py,registry.py,loop.py}`, `zebra_agent/knowledge.py`
- `zebra-tasks/zebra_tasks/web/kagi_news.py`, `agent/selector.py`, `knowledge/store_learned.py`,
  `pyproject.toml`
- `zebra-agent/workflows/daily_news_reading.yaml`
- `zebra-agent-web/zebra_agent_web/api/{daemon.py,goals.py,models.py}`, migration `0025`,
  `fixtures/routines/daily_news_reading.yaml`
