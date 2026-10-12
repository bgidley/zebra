## Context

Fourth web UI issue (#159 to #163). Uses the frame tokens and shared components from #159/#160 and the voice layer from #161.

## Decisions

- **Keep every contract.** URLs, form field names, `data-testid`s, HTMX targets, and the headings and uppercase trust level labels existing tests assert on stay. Only layout and styling change.
- **Segmented control from radios.** Each Trust row stays a plain form that works without JavaScript; Alpine only hides the reason and Save until the level changes.
- **Override hidden once freed.** Freeing permanently bypasses trust gates, so the emergency override no longer applies; showing it would mislead.
- **Diagram at natural width.** `generate_workflow_svg` caps width at 100%, which squeezed long workflows into an unreadable strip. Workflow detail overrides that with the SVG's own width and a scrolling panel; run pages are unchanged.
- **Bars computed in the view.** `_budget_bars()` turns budget status into widths so the template has no arithmetic.

## Risks

- Workflow-detail diagrams of very long workflows need horizontal scrolling; the steps list beside it is the readable summary.
- Indigo accents and older styling remain on pages not covered here until #163.
