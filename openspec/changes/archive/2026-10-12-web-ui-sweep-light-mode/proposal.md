## Why

After #159 to #162 the shell and key screens sit on the frame and voice tokens, but about 600 hard-coded Tailwind hue classes remained across ~30 templates and two Python modules, the workflow diagram had its own hex colours, a temporary v3-compat layer was still in place, and there was no light mode. This finishes the migration and records the rules. Issue #163.

## What Changes

- **Colour sweep**: every hue class maps onto a token (green to `ok`, red to `fail`, amber/yellow to `needs`, purple to `voice`, blue to a neutral, indigo accents to `ink`). `text-white` becomes `text-ground` on solid coloured backgrounds and `text-ink` elsewhere; two Alpine-bound buttons now set their text colour with their background.
- **Light mode**: dark stays the default; `prefers-color-scheme: light` redefines every token and mirrors the gray scale. `color-scheme` is set so native controls follow. Faint text and light `ok` were adjusted so every text token meets WCAG AA on `surface`, `ground` and `surface-2` in both themes.
- **Diagram** colours become token CSS variables (with the old hex as fallback), applied as `style` properties.
- **Run output** markdown styling uses the tokens.
- **Compat layer removed**: base defaults now use `line` borders and `faint` placeholders.
- **Copy**: em-dashes removed from visible UI text.
- **Docs**: `specs/web-ui-design.md` records the frame and voice rules.

## Capabilities

### New Capabilities
- `web-ui-theme`: light/dark theme, token-only colours, contrast guarantee.

### Modified Capabilities
<!-- none -->

## Impact

- `static/css/src/app.css`, ~30 templates, `form_tags.py`, `web_views.py`, `diagram.py`.
- New `tests/unit/test_theme.py`; new `specs/web-ui-design.md`.
