## 1. Sweep

- [x] 1.1 Map hue classes to tokens across templates, `form_tags.py`, `web_views.py`
- [x] 1.2 Fix Alpine-bound buttons so text colour moves with background
- [x] 1.3 Diagram colours via token CSS variables
- [x] 1.4 Run output markdown on tokens
- [x] 1.5 Remove em-dashes from visible copy

## 2. Theme

- [x] 2.1 Light palette and mirrored gray scale under `prefers-color-scheme: light`; `color-scheme`
- [x] 2.2 Adjust faint and light ok for WCAG AA
- [x] 2.3 Replace the compat layer with token base defaults

## 3. Tests and docs

- [x] 3.1 `test_theme.py`: light block completeness, AA contrast, primary button contrast, no hue classes, compat removed, diagram tokens
- [x] 3.2 Screenshots in both themes (desktop, light at phone width)
- [x] 3.3 `specs/web-ui-design.md`, `specs/AGENTS.md`, `specs/zebra-as-is.md`
