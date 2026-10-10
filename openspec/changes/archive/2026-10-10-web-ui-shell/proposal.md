## Why

The app shell is the stock Tailwind UI dark template. The nav is one flat list with no sense of what needs you. A fixed version bar covers the last ~24px of every page. The sign-in and setup pages show the full nav to signed-out visitors. On phones the page-header buttons wrap onto two lines. #159 added design tokens; this change puts the shell on them and adds the shared pieces later screens (#161, #162) build on. Issue #160.

## What Changes

- **Sidebar**: zebra-stripe brand mark, nav grouped into the core items, **Agent** (Workflows, Knowledge, Dream Cycles) and **Governance** (Trust, Values Tags, Ethics Audit). A new **Tasks** item shows how many goals are waiting on you. The count loads over HTMX from `/nav/needs-you/` so it never slows or breaks a page render.
- **Version info** moves from the fixed bottom bar into the sidebar footer, still clickable to show recent commits. Pages no longer have content hidden under it.
- **Bare layout** (`layouts/bare.html`) for sign-in, passkey setup and first-run setup: brand mark, centred card, quiet version footer, no nav.
- **Mobile top bar**: menu button, page title, and one primary action (Run goal). Dashboard secondary actions hide below `sm`.
- **Neutral frame**: Tailwind's `gray` scale is remapped in `@theme` to neutral values matching the frame tokens, so every existing page moves from blue-grey to the neutral frame without template edits.
- **Shared components**: `.btn` / `.btn-primary` / `.btn-quiet` / `.btn-danger`, `.panel`, state dot and certainty stripe partials, and a `|usd` money filter (2 decimals, `<$0.01` below a cent).

No URL, form field, `data-testid` or HTMX target changes.

## Capabilities

### New Capabilities
- `web-ui-shell`: app shell, bare layout, nav needs-you count, shared UI components and money filter.

### Modified Capabilities
- `version-footer`: version info lives in the sidebar footer (app pages) or the bare layout footer, not a fixed bottom strip.

## Impact

- New: `templates/layouts/bare.html`, `templates/partials/head_assets.html`, `partials/version_info.html`, `partials/nav_needs_you.html`, `components/state_dot.html`, `components/certainty.html`, `api/templatetags/format_tags.py`, view `nav_needs_you`, route `/nav/needs-you/`, icon `tray`.
- Changed: `base.html`, `_nav_link.html`, `nav_item.html`, `pages/auth_login.html`, `pages/auth_setup.html`, `pages/setup.html`, `pages/dashboard.html`, `static/css/src/app.css`.
