## Context

First of five web UI issues (#159 to #163) moving the UI toward a "frame and voice" design: a neutral frame for the human's controls and a voice layer for Zebra's own reasoning. This change only lays the foundation. Pages keep their layout.

## Decisions

- **Tailwind standalone binary, driven by a stdlib Python script.** No Node toolchain on the host or in the image. The binary is pinned and sha256-checked per platform, and cached under `~/.cache/zebra/tailwindcss/<version>/`. A failed download or checksum stops the build with a clear message. Committing the ~100MB binary was rejected; the build already needs the network for `uv sync`.
- **Compiled CSS is not committed.** It is built in the Dockerfile before `collectstatic`, and by a `css` lint-stage job so a broken build fails on branches rather than first in the master-only deploy. Developers run `scripts/build_css.py` (or `--watch`).
- **Explicit `@source` paths** (templates, Python modules, static JS) because utility classes also live in `form_tags.py`, `diagram.py`, `web_views.py` and `workflow-diagram.js`.
- **v3 compatibility layer** (border colour, placeholder colour, button cursor) plus `flex-shrink-0` renamed to `shrink-0`, so current pages render as before. Remove it in #163.
- **Zebra tokens in `@theme static`** so they are always emitted as CSS variables, even before templates use them. Dark values only; light mode lands in #163.
- **Icons inlined by a template tag** from vendored Phosphor SVGs instead of a sprite: no extra request, colour from `currentColor`, and a test that every used name is vendored. Unknown names render nothing and log an error rather than breaking a page.
- **Alpine pinned to 3.17.4**, the version prod's floating `3.x.x` tag resolved to, so behaviour does not change. Vendored files are integrity-guarded by git, not checksums.

## Risks

- Tailwind v4's grey palette is oklch, so greys shift very slightly from v3. Checked by screenshot on dashboard, run, trust and knowledge pages.
- The CI runner and image build need to reach GitHub releases on a cold cache.
