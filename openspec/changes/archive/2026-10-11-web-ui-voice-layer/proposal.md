## Why

Zebra will grow a personality over time, and the management tools should increasingly show what it is thinking. It already records a lot of reasoning: the ethics gates, the continuation call, the workflow choice, flagged concerns and the post-run ethics review. The UI hides almost all of it in raw task output. This change starts the voice layer by surfacing that reasoning, in Zebra's own words where it gives them. Issue #161; feeds #24 (personality config).

## What Changes

- **Producers record a voice line.** The ethics gate (input and plan), workflow selector, flag concerns, continuation assessor and the post-run ethics review prompt ask for two extra JSON fields: `voice` (one or two first-person sentences to the user) and `confidence` (0 to 1). They come back in the same LLM call. `zebra_tasks/agent/voice.py` normalises them, and they are stored only when the model supplies them, so voiceless outputs keep their old shape. Agent Main Loop bumped to v15 so the post-review prompt change reaches the live library.
- **Read model** `zebra_agent_web/api/thoughts.py`: `thoughts_for_process()` turns a run's recorded reasoning into ordered thoughts (voice line if present, otherwise the step's recorded reasoning, marked as such); `recent_thoughts()` builds a home feed from the user's most recent top-level runs. No LLM calls, no invented text.
- **UI**: a "Thought trail" panel on run detail and pending-run pages, an "On my mind" panel on the dashboard, and certainty stripes on Knowledge confidence. A certainty stripe appears only when Zebra recorded a confidence.

## Capabilities

### New Capabilities
- `web-ui-voice-layer`: recorded voice fields, the thoughts read model, and the trail / feed / knowledge stripe UI.

### Modified Capabilities
<!-- none -->

## Impact

- zebra-tasks: new `agent/voice.py`; prompts and outputs in `ethics_gate.py`, `selector.py`, `flag_concerns.py`, `continuation_assessor.py`, `record_ethics_review.py`.
- zebra-agent: `workflows/agent_main_loop.yaml` post-review prompt, version 14 to 15.
- zebra-agent-web: new `api/thoughts.py`, `components/thought.html`, `partials/thought_trail.html`, `partials/on_my_mind.html`; `web_views.py` (dashboard context, `parent_flow.thoughts`), `dashboard.html`, `run_detail.html`, `run_pending.html`, `knowledge_list.html`.
- Slightly longer LLM responses for these five steps (two short fields).
