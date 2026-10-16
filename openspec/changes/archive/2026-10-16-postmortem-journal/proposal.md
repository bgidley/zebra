## Why

When a goal fails, Zebra records the failure (#140) and may ask a human for help (#176), but
nothing turns the incident into a lesson. A later goal in the same situation repeats the same
mistake. Zebra itself asked: "After incidents, I write down what I learned into long-term memory
so I don't repeat it." Issue #175.

## What Changes

- New `write_postmortem` action: a cheap haiku call writes what happened, the root cause and the
  lesson, plus Zebra's voice line, and stores it as a `PostmortemEntry` in the `MemoryStore`.
  Never fails the goal; without an LLM nothing is stored. One postmortem per run.
- Three triggers:
  - **Failed run**: new `write_postmortem` step in the Agent Main Loop after `assess_and_record`
    (version 17). Successful runs skip it.
  - **Timeout / crash** (goal FAILED before the loop recorded it): the daemon and `AgentLoop`
    start the new system workflow *Postmortem*.
  - **Bad outcome flagged by the user**: rating a run 1 or 2 starts *Postmortem* in the
    background, with the user's feedback.
- Retrieval: `consult_memory` also searches lessons relevant to the goal (Oracle vector search,
  keyword overlap elsewhere). They go into the selector's memory context and are appended to the
  executed goal as `<lessons>`.
- Journal page `/journal/`: lessons newest first, in Zebra's voice, linked to the run.

## Capabilities

### New Capabilities
- `postmortem-journal`: learn lessons from failed, timed-out and badly rated goals, recall them on
  similar goals, and show them as a journal.

### Modified Capabilities
<!-- none -->

## Impact

- `zebra-agent`: `PostmortemEntry` (memory.py), `MemoryStore` methods, in-memory backend,
  `zebra_agent/postmortem.py` (trigger helper), `loop.py`, new `workflows/postmortem.yaml`,
  `agent_main_loop.yaml` v17.
- `zebra-tasks`: `agent/postmortem.py`, `consult_memory`, `execute_goal_workflow`, entry point.
- `zebra-agent-web`: `PostmortemModel` + migration, `DjangoMemoryStore`, embeddings table,
  daemon hook, `/journal/` page + nav.
