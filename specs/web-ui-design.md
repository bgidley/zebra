# Web UI design: the frame and the voice

Issues #159 to #163. Rules for anyone changing the web UI. The proposal and mocks live in the "Zebra Console Refresh" artifact; this file is the source of truth for the code.

## 1. Goal and scope

Zebra is meant to grow a personality (REQ-PEER-005, #24) and eventually be freed (REQ-TRUST-006). The UI is built as two layers so it can grow with it:

- **The frame** holds the human's controls: navigation, budget, trust, the kill switch, forms. It is neutral and predictable. Safety controls never take on a mood.
- **The voice** is Zebra's own words: first-person reasoning it recorded while working. It gets one colour the frame never uses, and its share of the screen should grow as trust grows.

Out of scope here: the personality config itself (#24) and a dream-cycle voice.

## 2. Tokens and theme

Defined once in `zebra-agent-web/static/css/src/app.css` (Tailwind v4 `@theme`), compiled by `scripts/build_css.py`.

| Token | Role |
|---|---|
| `ground`, `surface`, `surface-2`, `line` | Page, panels, raised/hover, borders |
| `ink`, `muted`, `faint` | Primary, secondary, meta text |
| `ok`, `fail`, `needs` | The only states colour may mean: succeeded, failed, waiting on you |
| `voice` | Zebra's own words, nothing else |

- **Dark is the default; light follows `prefers-color-scheme`.** The light block redefines every token and mirrors Tailwind's `gray` scale (950 page, 800 cards, 400 secondary text), so templates written with `gray-*` read the same in both themes.
- **Contrast:** every text token meets WCAG AA (4.5:1) on `surface`, `ground` and `surface-2` in both themes. `tests/unit/test_theme.py` enforces it; change a value and the test tells you.
- **No hue classes.** Don't write `text-red-400`, `bg-indigo-600`, `text-white` and so on. Use the tokens (`text-fail`, `bg-ok/15`, `border-needs/40`, `bg-ink text-ground`). The same test fails on any hard-coded hue class in templates, `form_tags.py` or `web_views.py`.
- The workflow diagram (`diagram.py`) uses the same tokens through CSS variables with hex fallbacks. Inline styles and `<style>` blocks may not hard-code colour values either.
- **Deliberate debt: two neutral vocabularies.** Older templates still use `gray-*` utilities, which work because the gray scale is remapped (and mirrored for light mode) to the frame. New code should use the frame tokens (`bg-surface`, `text-muted`, `border-line`); convert `gray-*` when touching a template rather than in a big-bang rewrite.

## 3. Components

| Piece | Use |
|---|---|
| `.btn`, `.btn-primary`, `.btn-quiet`, `.btn-danger`, `.btn-sm` | Buttons. One primary per screen; destructive actions use `.btn-danger` (outline) and confirm |
| `.panel` | A grouped section. Radius rule: panels 10px, controls 6px, dots and pills round |
| `components/state_dot.html` | `running` (pulsing ink), `ok`, `fail`, `needs`, with an accessible label |
| `components/certainty.html` | Certainty stripe: solid at 1.0, sparser hatching as confidence falls. Only where a confidence was recorded |
| `components/thought.html` | One voice-layer thought |
| `{% icon "name" %}` | Vendored Phosphor icons; never hand-draw SVG icons |
| `\|usd`, `\|ago` | `$1,234.50` / `<$0.01`; `12m ago` |

Typography: Geist for text, Geist Mono with tabular figures for money, counts, durations and IDs. Sentence-case section headings; uppercase only for trust level names.

## 4. The voice layer

- Reasoning steps record an optional first-person `voice` line and `confidence` in the same LLM call (`zebra_tasks/agent/voice.py`). No extra calls, no generated decoration.
- `api/thoughts.py` reads them. Where a step recorded no voice, the UI quotes its recorded reasoning and labels it as such.
- Never invent mood text or infer a confidence. The certainty stripe appears only for a recorded confidence.

## 5. Copy

Plain, specific, active voice. No em-dashes in UI copy. Name things by what the user recognises ("Needs you", not "pending human task instances").

## 6. Open questions

- When the personality config (#24) lands, it should drive the `voice` colour and tone. The token is the hook.
- A manual light/dark toggle (`data-theme`) if anyone wants to override the system setting.
