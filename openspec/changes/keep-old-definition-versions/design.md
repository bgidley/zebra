## Context

Definition ids are `sha256(name:version)[:16]` (`zebra.definitions.loader._generate_id`); each
process stores its `definition_id`, and the engine and web views load it by that id.
`WorkflowLibrary.copy_builtin_workflows` replaces an installed YAML when the built-in has a higher
version and returns the upgraded names. Startup then deleted every `ProcessDefinitionModel` row
with those names "so the engine reloads them from YAML", which also removed the rows running
processes point at.

## Decision

Drop the eviction. Old rows are harmless (a different id) and are needed by any process still on
that version. Name lookups that remain (`/dreams/`, `/bugs/`, improvement dedupe) collect all ids
for a name, so they now keep runs from earlier versions too.

The install step moves into `install_builtin_workflows()` so a test can run the real upgrade path
against `DjangoStore`.

## Risks

- The definitions table grows by one row per built-in version bump. That's negligible.
