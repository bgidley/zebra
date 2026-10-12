## Context

Last of the web UI issues (#159 to #163). Rules are in `specs/web-ui-design.md`.

## Decisions

- **Mechanical sweep with one rule per hue**, run per class attribute so `text-white` could see its own element's background. Leftover tokens in JS strings and Python class strings got the same mapping. Dynamic Alpine backgrounds were fixed by hand.
- **Mirror the gray scale for light mode** rather than rewriting templates: templates say "gray-800 card, gray-400 secondary text", and the light block maps those roles to light values. The override is unlayered so it beats the `@theme` defaults.
- **Contrast is a test, not a review step.** `test_theme.py` parses the token values from the stylesheet and computes WCAG ratios, so a later palette tweak can't silently regress.
- **Diagram colours via `style`, not presentation attributes**, because `var()` in SVG presentation attributes is not reliable across browsers.
- **No manual theme toggle yet**: the system setting covers it; a `data-theme` override can follow if wanted.

## Risks

- Mapping blue to neutral loses blue "info" accents; state is now carried by the dot and label.
- Tinted chips (`bg-<token>/15`) look lighter than the old dark-900 chips; checked by screenshot in both themes.
