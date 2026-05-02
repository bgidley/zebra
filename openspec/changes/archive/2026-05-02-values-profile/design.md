## Context

The Zebra agent enforces Kantian ethics gates on every goal (`zebra-tasks/zebra_tasks/agent/ethics_gate.py`, wired into `agent_main_loop.yaml` at steps 2, 5, and 8). Those gates are stateless — they evaluate the action against universal principles, with no knowledge of the specific human's values. F18 introduces persistent, per-user values that REQ-ETH-003 will later plumb into those gate prompts.

Existing scaffolding we can lean on:

- Per-user storage: `user_id` namespacing across all stores via contextvars (`zebra_agent_web/middleware.py`), shipped in F6.
- JSON-schema-driven human task forms: `zebra.forms` + `human_task_form.html`. Single-step today; multi-step is achieved by chaining human tasks in a workflow.
- Pluggable storage interfaces: `MemoryStore`, `MetricsStore` in `zebra_agent/storage/interfaces.py` with In-Memory + Django backends.
- System-workflow allowlist: `_is_system_workflow` in `zebra_agent/loop.py` excludes internal workflows from LLM selection.

What does **not** exist: a multi-step wizard pattern, a `/profile/` URL section, or any concept of a tag taxonomy.

## Goals / Non-Goals

**Goals:**

- Per-user, versioned values profile (core values, ethical positions, priorities, deal-breakers).
- Free-form text expression + LLM-extracted structured tags (hybrid taxonomy).
- Wizard UI for both first capture and edit, implemented as a Zebra workflow.
- Foundation for taxonomy learning (`candidate → promoted` lifecycle).
- Storage abstraction (`ProfileStore`) so the future ethics gate (REQ-ETH-003) can read profiles without driver-level coupling.

**Non-Goals:** see `proposal.md` (gate consumption, hard local-first, promotion UI, dedicated CLI).

## Decisions

### D1. Soft local-first (not hard)

`REQ-ETH-002` defers to `REQ-PRIN-005` ("data stays on the human's local device by default"). We adopt the **soft** reading: per-user DB-row isolation via existing `user_id` namespacing. The **hard** reading (device-local SQLite + opt-in cloud sync) is a Phase-4 deployment-architecture concern and would expand F18 indefinitely.

### D2. Versioning: profile + immutable version table (Option A)

`ValuesProfile` (one per user, mutable pointer) + `ValuesProfileVersion` (immutable, monotonic `version_number`). The alternative considered was snapshotting only into ethics decisions (Option B); rejected because REQ-ETH-002 explicitly states profiles are versioned (decision-side snapshots wouldn't satisfy the literal requirement) and a profile-side history enables a "show diff" / "restore" UI.

### D3. Hybrid taxonomy with learning

Each tag is field-scoped (one of `core_values`, `ethical_positions`, `priorities`, `deal_breakers`) and has `status ∈ {seeded, promoted, candidate}`. The extraction LLM sees the approved set (`seeded + promoted`) as anchors and may suggest new candidates from free-form text. Alternative considered: pure free-form (rejected — gate gets no structure) or pure fixed (rejected — taxonomy goes stale). Hybrid is the only option that supports both human expression and gate-side mechanical matching.

### D4. Workflow-as-wizard, both for capture and edit (Pure-A)

The wizard is `values_profile_wizard.yaml`. The same workflow runs for first capture and edit; edit mode is signalled by passing `existing_profile_version_id` in the initial process properties. Each save is a process — audit trail comes free. Alternative considered: Django form-wizard or a flat editor for edits; rejected to preserve "every change is a process" symmetry, which fits the project's dogfooding stance.

### D5. Pre-population via dedicated task action

A new task action `load_values_profile` reads `ProfileStore` and writes the current text/tags into process properties. Each form step's JSON schema then uses `default: "{{existing_profile.core_values_text}}"` to pre-fill. Alternative considered: pass JSON in initial process properties from the view; rejected because it leaks model knowledge into the view layer, and a task action keeps the workflow self-contained.

### D6. LLM-bootstrap of starter taxonomy

A one-time `manage.py bootstrap_values_taxonomy` command calls an LLM to draft a starter taxonomy across the four fields, writes it to `zebra-agent-web/fixtures/values_taxonomy_seed.yaml`, and is reviewed by hand before commit. A data migration loads the fixture into `Tag` rows on first `migrate`. Alternatives: empty seed (gate weak from day 1), hand-curated (high effort, brittle). Bootstrap is the cheapest path to a non-empty anchor set.

### D7. Tag-extraction failure handled by routing, not code

`extract_values_tags` always returns success — even when the LLM call fails or returns empty. The review step (step 7) shows whatever tags exist (possibly none) and lets the user fill in by hand. No "fail" branch in the workflow; this is a workflow-level decision per the user's framing.

### D8. Promotion mechanism deferred

F18 stores candidate tags and increments `usage_count` on confirmation. The actual promotion (UI/command/policy) is out of scope; tracked in a follow-up issue. Without this, the candidate table will grow but doesn't break anything.

### D9. `ProfileStore` is a new interface, not an extension of `MemoryStore`

The values profile is identity/preferences, not a record of past actions. Conceptually distinct, so it gets its own ABC + In-Memory + Django pair, alongside the existing two stores.

### D10. New task actions live in `zebra-tasks/zebra_tasks/agent/`

`load_values_profile`, `extract_values_tags`, `save_values_profile` all sit under the agent subdirectory next to existing agent-loop actions. They're registered as `zebra.tasks` entry points in `zebra-tasks/pyproject.toml`.

## Data Model Changes

```
ValuesProfile               ValuesProfileVersion          Tag
─────────────              ────────────────────────       ──────────────────
user_id  (FK, OneToOne)     profile_id (FK)               field      (str, indexed)
current_version_id (FK→Ver) version_number (int)          slug       (str)
created_at                  created_at                    label      (str)
updated_at                  created_via                   description (text, nullable)
                            core_values_text              status     (seeded|promoted|candidate)
                            core_values_tags (JSON)       usage_count (int, default 0)
                            ethical_positions_text        created_at
                            ethical_positions_tags        promoted_at (nullable)
                            priorities_text
                            priorities_tags
                            deal_breakers_text
                            deal_breakers_tags
                            tags_extracted_at (nullable)
                            tags_extraction_model (nullable)
```

Three new tables in `zebra-agent-web/zebra_agent_web/api/models.py`. Migrations are standard Django. Tag has a unique index on `(field, slug)`.

## Interface / Behaviour Changes

- **New task actions** (entry points in `zebra-tasks/pyproject.toml`):
  - `load_values_profile` — reads ProfileStore, writes `existing_profile.*` into properties; outputs `{found: bool}`.
  - `extract_values_tags` — LLM call; output is `{<field>: {approved_tags: [...], candidate_tags: [...]}}`.
  - `save_values_profile` — writes `ValuesProfileVersion` + bumps `ValuesProfile.current_version`; persists user-confirmed tags; increments `usage_count` on confirmed tags; persists new candidates.
- **New system workflow:** `zebra-agent/workflows/values_profile_wizard.yaml`. Add `"Values Profile Wizard"` to `_is_system_workflow` in `zebra_agent/loop.py`.
- **New URL route:** `path("profile/values/", ValuesProfileWizardStartView.as_view(), name="values_profile_wizard")` in `zebra-agent-web/zebra_agent_web/urls.py`. The view starts a process running the wizard workflow with the appropriate `mode` and (if present) `existing_profile_version_id`, then redirects to the standard task UI.
- **New management command:** `zebra-agent-web/zebra_agent_web/api/management/commands/bootstrap_values_taxonomy.py`.
- **New storage interface:** `ProfileStore` ABC in `zebra-agent/zebra_agent/storage/interfaces.py`; `InMemoryProfileStore` in `zebra_agent/storage/profile.py`; `DjangoProfileStore` in `zebra-agent-web/zebra_agent_web/api/stores.py`. Inject via `engine.extras["__profile_store__"]` in `AgentLoop.__init__` (and the daemon path).
- **specs/zebra-as-is.md updates:** new section after the "Memory" section covering values profile + taxonomy + wizard workflow + ProfileStore.

## Risks / Trade-offs

- **LLM extraction noise → candidate-tag bloat.** Mitigation: review step gates persistence (only user-confirmed candidates are saved). Cap LLM output to N candidates per field (e.g. 5).
- **Edit ergonomics under Pure-A.** Tweaking one line means walking through the 8-step wizard. Mitigation: every step is pre-populated, so the user is mostly clicking "Next". If this becomes painful in practice, a flat editor can be added without invalidating the data model.
- **Bootstrap requires an LLM call during installation prep.** Mitigation: it's one-time, manual, output is committed to the repo as a fixture. Subsequent installs load the fixture, no LLM call needed.
- **No automatic promotion** means the gate (REQ-ETH-003) initially only sees seeded tags. Mitigation: bootstrap should produce a sufficient starter set; promotion ticket is queued.
- **Tag table growth.** Without promotion/demotion, the `Tag` table grows indefinitely with `candidate` rows. Mitigation: `usage_count` is indexed; queries for "approved" tags filter on `status`. A future cleanup pass can prune `candidate` rows with `usage_count == 0` after N days.

## Migration Plan

1. Migrations create the three new tables.
2. Maintainer runs `manage.py bootstrap_values_taxonomy` once locally, hand-reviews `fixtures/values_taxonomy_seed.yaml`, commits it.
3. A data migration loads the fixture into `Tag` rows with `status="seeded"` on first `migrate`.
4. The wizard workflow YAML is shipped under `zebra-agent/workflows/`.
5. Entry-point registration via `uv sync --all-packages`.
6. **Rollback:** the ethics gate is unchanged; dropping the three new tables leaves the existing system functional. The system workflow allowlist entry can be removed without cascading effects.

## Open Questions

- Should `extract_values_tags` cap candidates per field (suggest: 5)? Easy to add later — leave uncapped initially and observe.
- Should the wizard workflow expose `next_route` shortcuts to skip steps when pre-populated values are unchanged, or always walk the full sequence? Default to full sequence; revisit if edit ergonomics become a real problem.
