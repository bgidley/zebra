## Why

The Zebra agent already runs Kantian ethics gates on every goal (REQ-ETH-001), but those gates have no knowledge of the human's personal values. We can detect actions that are universally wrong, but not actions that conflict with this specific user's principles, priorities, or deal-breakers. Closes #18 (REQ-ETH-002) by introducing the values profile data model and capture/edit experience that REQ-ETH-003 will later consume.

## What Changes

- New `ValuesProfile` and `ValuesProfileVersion` Django models — per-user, immutable versioning
- New `Tag` model — field-scoped, hybrid taxonomy with `seeded` / `promoted` / `candidate` lifecycle
- New `ProfileStore` abstract interface, with `DjangoProfileStore` and `InMemoryProfileStore` backends
- Three new task actions: `load_values_profile`, `extract_values_tags`, `save_values_profile`
- New system workflow `values_profile_wizard.yaml` — used for both first capture and edit
- New web entrypoint `/profile/values/` — starts a wizard process (capture or edit mode)
- New `manage.py bootstrap_values_taxonomy` — one-time LLM-driven seeder producing a reviewable starter taxonomy fixture

## Capabilities

### New Capabilities

- `values-profile`: Per-user, versioned profile of core values, ethical positions, priorities, and deal-breakers — captured and edited via a Zebra workflow
- `values-taxonomy`: Hybrid tag taxonomy (fixed + learned) supporting LLM-assisted extraction from free-form text, with a candidate→promoted lifecycle to enable learning over time

### Modified Capabilities

<!-- None — F18 is purely additive. Ethics-gate consumption (REQ-ETH-003) is a separate change. -->

## Non-goals

- **Wiring the values profile into the ethics gate.** That is REQ-ETH-003, a follow-up change. F18 delivers data + UI only.
- **Hard local-first storage** (strict reading of REQ-PRIN-005). F18 uses the existing per-user DB namespacing pattern. Device-local deployment is a Phase-4 architecture concern.
- **Promotion UI for candidate tags.** A follow-up issue covers reviewing and promoting candidate tags. F18 only accumulates them.
- **CLI parity.** F18 ships the workflow + web entrypoint; CLI access piggybacks on the workflow runner without dedicated UX work.

## Impact

- New code in `zebra-agent-web/` (models, migrations, views), `zebra-agent/zebra_agent/storage/` (ProfileStore + impls), `zebra-tasks/zebra_tasks/agent/` (3 actions), `zebra-agent/workflows/values_profile_wizard.yaml`
- `_is_system_workflow` allowlist updated in `zebra_agent/loop.py`
- New section in `specs/zebra-as-is.md` covering values profile + taxonomy
- One LLM call added per profile save (extract_values_tags); cost is per edit, not per agent run
