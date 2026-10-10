# web-ui-shell Specification

## Purpose
TBD - created by archiving change web-ui-shell. Update Purpose after archive.

## Requirements

### Requirement: Grouped navigation with a needs-you count
The app shell SHALL group navigation into core items (Dashboard, Tasks, Run Goal, Activity), an **Agent** group (Workflows, Knowledge, Dream Cycles) and a **Governance** group (Trust, Values Tags, and Ethics Audit for staff). The Tasks item SHALL link to `/tasks/` and SHALL show the number of running goals waiting on a human task, loaded from `/nav/needs-you/` after the page renders.

#### Scenario: Groups render in order
- **WHEN** a staff user loads any page that extends `base.html`
- **THEN** the nav shows the core items, then an "Agent" group, then a "Governance" group containing Ethics Audit

#### Scenario: Count shown when goals wait on you
- **WHEN** two running goals each have a READY human task and the browser requests `/nav/needs-you/`
- **THEN** the response shows the count 2

#### Scenario: No badge when nothing waits
- **WHEN** no running goal has a READY human task
- **THEN** `/nav/needs-you/` returns an empty badge

#### Scenario: Store failure does not break the page
- **WHEN** loading running processes raises an error
- **THEN** `/nav/needs-you/` returns HTTP 200 with an empty badge and the error is logged

### Requirement: Bare layout for signed-out pages
The sign-in, passkey setup and first-run setup pages SHALL use a bare layout with the brand mark and the page card, and SHALL NOT render the app navigation.

#### Scenario: Sign-in has no nav
- **WHEN** a signed-out visitor loads `/auth/login/`
- **THEN** the page contains the sign-in card and no `<nav>` element

### Requirement: Mobile top bar with one primary action
Below the `lg` breakpoint the shell SHALL show a top bar with a menu button, the page title and a single primary "Run goal" action. Button labels SHALL NOT wrap.

#### Scenario: Phone width
- **WHEN** a page is rendered at 390px wide
- **THEN** the top bar shows the menu button, title and Run goal, and opening the menu reveals the nav

### Requirement: Shared UI components
The web UI SHALL provide shared button, panel, state dot and certainty stripe components, and a `usd` template filter. `usd` SHALL format amounts with two decimals and a thousands separator, render amounts above zero but below one cent as `<$0.01`, and render empty values as an empty string.

#### Scenario: Money formatting
- **WHEN** the `usd` filter receives `1234.5`, `0.004`, `0`, and `None`
- **THEN** it renders `$1,234.50`, `<$0.01`, `$0.00` and an empty string

#### Scenario: Certainty stripe density
- **WHEN** the certainty component receives confidence 1.0, 0.8, 0.6 and 0.3
- **THEN** it renders the solid, dense, medium and sparse stripe variants, each with the confidence as its accessible label

### Requirement: Neutral frame palette
The stylesheet SHALL remap Tailwind's `gray` scale to neutral values aligned with the frame tokens, so existing pages use the neutral frame without template changes.

#### Scenario: Grey utilities are neutral
- **WHEN** the stylesheet source is read
- **THEN** it defines `--color-gray-50` through `--color-gray-950`, and `--color-gray-950` equals the `ground` token
