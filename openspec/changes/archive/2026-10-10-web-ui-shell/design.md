## Context

Second of the web UI issues (#159 to #163). Builds on the #159 tokens and icon tag.

## Decisions

- **Remap `gray` instead of rewriting templates.** Every page uses `gray-*` utilities. Redefining the scale in `@theme` (950 = ground, 850 = surface, 800 = surface-2, 400 = muted, 500 = faint) moves the whole UI onto the neutral frame in one place. Indigo stays until #162/#163 replace it page by page.
- **Needs-you count over HTMX.** The count reuses `_running_activities` (same definition of "waiting on you" as the dashboard) but is fetched after page load from `/nav/needs-you/`. A slow or failing store can't delay or break any page. The count is goals waiting, not tasks, matching what `/tasks/` lists.
- **Components as CSS classes plus small partials.** Buttons and panels are `@layer components` classes because their content varies. State dot and certainty stripe are partials because they map a value to a variant and an accessible label.
- **Nav labels unchanged.** Existing labels stay for muscle memory; grouping and the new Tasks item are additive.
- **Version info keeps its fetch-once behaviour.** One Alpine component, rendered in the sidebar footer or the bare layout footer, opens its panel upward.

## Risks

- Remapped greys change contrast slightly. gray-400 on gray-800 stays above 4.5:1. Checked by screenshot.
- The count adds one request per page view. It's cheap (running processes only) and does nothing when nothing runs.
