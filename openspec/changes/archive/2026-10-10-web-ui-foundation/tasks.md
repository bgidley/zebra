## 1. Build

- [x] 1.1 `scripts/build_css.py` (pinned Tailwind v4.3.3, sha256 per platform, cache, `--watch`)
- [x] 1.2 `static/css/src/app.css` with sources, tokens, fonts, legacy greys
- [x] 1.3 Dockerfile step before `collectstatic`; `css` CI job; ignore `static/css/app.css`

## 2. Assets

- [x] 2.1 Vendor Geist and Geist Mono woff2 with licence
- [x] 2.2 Vendor HTMX 2.0.4 and Alpine 3.17.4; load them from `base.html` and `setup.html`
- [x] 2.3 Vendor the Phosphor icons in use, with licence

## 3. Templates

- [x] 3.1 `{% icon %}` tag
- [x] 3.2 Nav, stat card and shell icons via the tag; literal stat-card colours

## 4. Tests and docs

- [x] 4.1 Unit tests: icon tag, vendored-icon scan, no CDN references, nav icons, build script checksum handling
- [x] 4.2 Update `specs/zebra-as-is.md`, `zebra-agent-web/AGENTS.md`, README dev instructions
