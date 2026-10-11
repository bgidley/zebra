## ADDED Requirements

### Requirement: Reasoning steps record Zebra's voice
The ethics gate, workflow selector, flag-concerns, continuation assessor and post-run ethics review SHALL ask the model, in the same call, for a `voice` field (one or two first-person sentences addressed to the user) and a `confidence` field (0.0 to 1.0). The stored output SHALL include each field only when the model supplied a valid value. `voice` SHALL be whitespace-normalised and clipped to 400 characters, and `confidence` SHALL be clamped to 0.0 to 1.0.

#### Scenario: Voice recorded
- **WHEN** the workflow selector's model returns a choice with `voice` and `confidence` 0.8
- **THEN** the stored `selection` includes that `voice` and `confidence` 0.8

#### Scenario: No voice supplied
- **WHEN** a reasoning step's model omits `voice` and `confidence`
- **THEN** the stored output has neither key and is otherwise unchanged

#### Scenario: Invalid values dropped
- **WHEN** the ethics gate's model returns `voice` 7 and `confidence` "very"
- **THEN** the stored assessment has neither key

### Requirement: Thoughts read model
The web app SHALL derive a run's thoughts from its Agent Main Loop process properties, in step order: ethics input, continuation (only for real continuations), workflow choice, planning concerns, ethics plan and post-run review. A thought's text SHALL be the recorded `voice` when present, otherwise the step's recorded reasoning, and SHALL be flagged as voice or recorded reasoning. A thought SHALL carry a confidence only when one was recorded. It SHALL never call an LLM or generate text.

#### Scenario: Voice preferred
- **WHEN** the workflow choice recorded a `voice` and reasoning
- **THEN** its thought text is the voice line and it is flagged as voice

#### Scenario: Continuation not repeated
- **WHEN** a continuation's rationale is also written as the selection reasoning
- **THEN** only the continuation thought is shown

#### Scenario: Quiet steps
- **WHEN** an ethics gate approved with no concerns and recorded no voice
- **THEN** its thought is marked quiet

### Requirement: Thought trail on run pages
Run detail and pending-run pages SHALL show a "Thought trail" panel listing the run's thoughts in step order, including quiet ones, and SHALL omit the panel when there are none.

#### Scenario: Trail shown
- **WHEN** a run recorded reasoning at five steps
- **THEN** the run page shows five thoughts in step order

### Requirement: On my mind feed
The dashboard SHALL show an "On my mind" panel with the current user's most recent non-quiet thoughts, newest run first, each linking to its run, with an empty state when there are none. A failure loading the feed SHALL NOT break the dashboard.

#### Scenario: Feed scoped to the user
- **WHEN** another user's run recorded a voice line
- **THEN** it does not appear in the current user's feed

### Requirement: Certainty stripes
Wherever a thought or knowledge entry has a recorded confidence, the UI SHALL show the certainty stripe for it (solid at 1.0, denser to sparser hatching as confidence falls). Thoughts without a recorded confidence SHALL show a plain marker instead.

#### Scenario: Knowledge confidence
- **WHEN** the Knowledge page lists an entry with confidence 0.5
- **THEN** its confidence cell shows the medium certainty stripe and "0.50"
