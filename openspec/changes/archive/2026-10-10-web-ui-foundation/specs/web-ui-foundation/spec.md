## ADDED Requirements

### Requirement: Compiled stylesheet
The web UI SHALL style pages from a stylesheet compiled at build time from `static/css/src/app.css` by a pinned Tailwind v4 binary. Pages SHALL NOT load scripts or stylesheets from a CDN.

#### Scenario: Page links the compiled stylesheet
- **WHEN** any page that extends `base.html`, or the setup page, is rendered
- **THEN** it links `/static/css/app.css` and contains no `cdn.tailwindcss.com` or `unpkg.com` reference

#### Scenario: Build verifies the binary
- **WHEN** `scripts/build_css.py` downloads the Tailwind binary and its sha256 does not match the pinned value
- **THEN** the build fails without running the binary

#### Scenario: Classes outside templates are compiled
- **WHEN** a utility class appears only in a Python module or a static JavaScript file under `zebra-agent-web`
- **THEN** the compiled stylesheet includes it

### Requirement: Design tokens
The stylesheet SHALL define colour tokens for the frame (`ground`, `surface`, `surface-2`, `line`, `ink`, `muted`, `faint`), the states `ok`, `fail` and `needs`, and a `voice` colour reserved for text Zebra writes in its own words. It SHALL set Geist as the sans font and Geist Mono as the mono font, both served from `static/fonts`.

#### Scenario: Token utilities exist
- **WHEN** a template uses `bg-surface`, `text-voice` or `font-mono`
- **THEN** the compiled stylesheet contains those utilities

### Requirement: Icon template tag
The web UI SHALL provide an `{% icon "name" %}` tag that renders a vendored Phosphor regular icon as inline SVG with `fill="currentColor"`, `aria-hidden="true"` and any `class` passed in. An unknown name SHALL render nothing and log an error.

#### Scenario: Known icon
- **WHEN** a template renders `{% icon "moon" class="h-5 w-5" %}`
- **THEN** the output is an `<svg>` with `class="h-5 w-5"` and `aria-hidden="true"`

#### Scenario: Every icon used in templates is vendored
- **WHEN** templates are scanned for `{% icon %}` names
- **THEN** each name has a vendored SVG file

#### Scenario: Nav items all have icons
- **WHEN** the base layout renders for a staff user
- **THEN** every nav item, including Knowledge, Trust and Ethics Audit, contains an icon
