## Why

The web UI loads Tailwind from the Play CDN, which compiles CSS in the browser on every page load and is not meant for production. HTMX and Alpine also come from a CDN, and Alpine's `3.x.x` tag floats. There are no design tokens and no set font. There are 77 hand-copied SVG icons, and three nav icons are missing. A dynamic `bg-{{ color }}-600` class only works because the CDN compiles at runtime. Every later UI change in the "frame and voice" direction (#160 to #163, #24) needs a real build and shared tokens first. Issue #159.

## What Changes

- `scripts/build_css.py` downloads a pinned Tailwind v4 standalone binary (sha256-checked, cached) and compiles `zebra-agent-web/static/css/src/app.css` to `static/css/app.css`. The output is not committed. The Dockerfile builds it before `collectstatic`, and a new `css` CI job in the lint stage builds it on every pipeline.
- `app.css` declares design tokens in `@theme`: frame neutrals, state colours (`ok`, `fail`, `needs`) and a reserved `voice` colour for Zebra's own words. It also carries the existing custom greys so current pages look the same.
- Geist and Geist Mono are self-hosted (`static/fonts`, OFL) and become the default sans and mono fonts.
- HTMX 2.0.4 and Alpine 3.17.4 (the version prod's floating tag resolves to today) are vendored into `static/vendor` and loaded from there. No CDN scripts remain.
- A `{% icon "name" %}` template tag renders vendored Phosphor (regular) SVGs inline. Nav, stat-card and shell icons use it, which fixes the missing Knowledge, Trust and Ethics Audit icons.
- `stat_card.html` uses literal colour classes.

Layout and colour redesign are out of scope (later issues).

## Capabilities

### New Capabilities
- `web-ui-foundation`: compiled stylesheet, design tokens, self-hosted fonts and vendored scripts, and the icon template tag.

### Modified Capabilities
<!-- none -->

## Impact

- New: `scripts/build_css.py`, `zebra-agent-web/static/css/src/app.css`, `static/fonts/*`, `static/vendor/*`, `zebra_agent_web/icons/phosphor/*.svg`, `api/templatetags/icon_tags.py`.
- Changed: `templates/base.html`, `templates/pages/setup.html`, `partials/_nav_link.html`, `components/stat_card.html`, `Dockerfile`, `.gitlab-ci.yml`, `.gitignore`.
- Local development needs `uv run python scripts/build_css.py` (or `--watch`) once before running the server.
