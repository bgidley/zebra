## ADDED Requirements

### Requirement: Light and dark themes
The web UI SHALL render in dark by default and in light when the viewer's system prefers light, by redefining every colour token and the gray scale under `prefers-color-scheme: light`, and SHALL set `color-scheme` so native form controls follow the theme.

#### Scenario: Light preference
- **WHEN** a page loads in a browser that prefers light
- **THEN** the page uses the light token values and no text renders in pure white

#### Scenario: Every token has a light value
- **WHEN** the stylesheet source is read
- **THEN** the light block defines every frame, state and voice token and every gray step

### Requirement: Text contrast
Every text token (`ink`, `muted`, `faint`, `ok`, `fail`, `needs`, `voice`) SHALL have a contrast ratio of at least 4.5:1 against `surface`, `ground` and `surface-2` in both themes, and primary button text (`ground` on `ink`) SHALL be at least 7:1.

#### Scenario: Faint text in dark mode
- **WHEN** the contrast of `faint` on `surface-2` is computed for the dark theme
- **THEN** it is at least 4.5:1

### Requirement: Token-only colours
Templates, `form_tags.py` and `web_views.py` SHALL NOT use hard-coded Tailwind hue or white colour classes; colour SHALL come from the frame, state and voice tokens. The workflow diagram SHALL use the tokens through CSS variables.

#### Scenario: Regression guard
- **WHEN** a template adds `text-red-400`
- **THEN** the theme test fails and names the file

#### Scenario: Diagram follows the theme
- **WHEN** a workflow diagram is generated
- **THEN** its colours are `var(--color-…)` references with hex fallbacks
