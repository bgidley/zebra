## MODIFIED Requirements

### Requirement: Version footer is shown on every page
The system SHALL show the short git commit hash and date on every page, in a compact, unobtrusive style (small monospace text, muted colour). On pages that extend `base.html` it SHALL sit in the sidebar footer rather than a fixed strip, so it never covers page content. On pages using the bare layout (sign-in, passkey setup, first-run setup) it SHALL sit in the page footer.

#### Scenario: Footer visible on dashboard
- **WHEN** an authenticated user visits any page that extends `base.html`
- **THEN** the sidebar footer contains the version element with the short commit hash
- **THEN** no fixed-position version strip is rendered

#### Scenario: Footer shown without authentication on setup page
- **WHEN** the setup page is rendered (before any user exists)
- **THEN** the version element is still visible in the bare layout footer
