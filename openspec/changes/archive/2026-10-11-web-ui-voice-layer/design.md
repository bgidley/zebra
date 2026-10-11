## Context

Third web UI issue (#159 to #163), and the first step toward the management tools reflecting Zebra's inner thoughts. The frame (#159, #160) holds the human's controls; the voice layer is Zebra's own words.

## Decisions

- **Ask for the voice in the call that already happens.** Each reasoning step gains two optional JSON fields; there are no extra LLM calls just to decorate the UI. Older runs and models that omit the fields degrade to quoting the step's recorded reasoning, visibly marked "recorded reasoning".
- **Present-only fields.** `voice_fields()` adds keys only when supplied, so existing consumers and exact-shape tests see unchanged outputs for voiceless responses.
- **Confidence is never inferred.** Only knowledge and voice-bearing outputs have a confidence. Everything else gets a plain marker, never a guessed stripe.
- **Read model in the web app, not a new table.** Thoughts are derived from process properties on read. A store table can come later if the feed needs history beyond recent runs.
- **Feed query.** The 25 most recently updated top-level processes for the user (root `parent_process_id` may be NULL or empty), newest first, keeping non-quiet thoughts. Processes without reasoning simply yield nothing.
- **Workflow version bump** (14 to 15) so the post-review prompt change is copied into the live library.

## Risks / follow-ups

- The dream cycle does not record a voice yet; its summaries stay on `/dreams/`. Follow-up once the personality config (#24) shapes the voice.
- Longer responses for five steps (a sentence and a number each).
- The run pages overflow at phone width because of the existing task panels (pre-existing; noted on #162).
