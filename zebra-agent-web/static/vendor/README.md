# Vendored front-end assets

Served by WhiteNoise from `/static/`. Pinned on purpose: bump by replacing the
file and updating the version in its name and in the templates that load it.

| File | Source | Licence |
|------|--------|---------|
| `htmx-2.0.4.min.js` | `htmx.org@2.0.4/dist/htmx.min.js` | 0BSD |
| `alpine-3.17.4.min.js` | `alpinejs@3.17.4/dist/cdn.min.js` | MIT |
| `../fonts/geist-latin-wght-normal.woff2` | `@fontsource-variable/geist@5.3.0` | OFL 1.1 (`../fonts/OFL.txt`) |
| `../fonts/geist-mono-latin-wght-normal.woff2` | `@fontsource-variable/geist-mono@5.3.0` | OFL 1.1 |
| `zebra_agent_web/icons/phosphor/*.svg` | `@phosphor-icons/core@2.1.1/assets/regular` | MIT (`LICENSE` beside them) |

The stylesheet `../css/app.css` is not vendored: `scripts/build_css.py` compiles
it from `../css/src/app.css` with a pinned Tailwind binary.
