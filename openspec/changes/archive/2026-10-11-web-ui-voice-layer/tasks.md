## 1. Producers

- [x] 1.1 `zebra_tasks/agent/voice.py`: schema fields, `extract_voice()`, `voice_fields()`
- [x] 1.2 Ethics gate (both schemas), selector, flag concerns, continuation assessor record voice/confidence
- [x] 1.3 Post-review prompt + `normalise_post_review` keep voice; Agent Main Loop v15

## 2. Read model and UI

- [x] 2.1 `api/thoughts.py`: `thoughts_for_process()`, `recent_thoughts()`
- [x] 2.2 `components/thought.html`, `partials/thought_trail.html`, `partials/on_my_mind.html`
- [x] 2.3 Trail on run detail and pending-run pages; On my mind on the dashboard
- [x] 2.4 Certainty stripes and voice colour on Knowledge

## 3. Tests and docs

- [x] 3.1 zebra-tasks: normalisation, prompts, each producer stores voice, post-review, version bump
- [x] 3.2 zebra-agent-web: read model, feed query (order, children, user scope, bad rows), rendering, knowledge stripes
- [x] 3.3 Update `specs/zebra-as-is.md`, `zebra-tasks/AGENTS.md`, `zebra-agent-web/AGENTS.md`
