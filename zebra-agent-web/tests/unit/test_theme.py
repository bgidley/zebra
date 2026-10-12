"""Tests for the light/dark theme and colour sweep (#163)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2]
CSS = (WEB / "static" / "css" / "src" / "app.css").read_text()
TOKENS = (
    "ground",
    "surface",
    "surface-2",
    "line",
    "ink",
    "muted",
    "faint",
    "ok",
    "fail",
    "needs",
    "voice",
)
TEXT_TOKENS = ("ink", "muted", "faint", "ok", "fail", "needs", "voice")
BACKGROUNDS = ("surface", "ground", "surface-2")


def _tokens(block: str) -> dict[str, str]:
    return dict(re.findall(r"--color-([a-z0-9-]+):\s*(#[0-9a-f]{6})", block))


def _dark() -> dict[str, str]:
    start = CSS.index("@theme static")
    return _tokens(CSS[start : CSS.index("}", start)])


def _light() -> dict[str, str]:
    return _tokens(CSS[CSS.index("@media (prefers-color-scheme: light)") :])


def _luminance(hex_colour: str) -> float:
    def channel(pair: str) -> float:
        c = int(pair, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(hex_colour[i : i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_light_mode_redefines_every_token_and_the_gray_scale():
    light = _light()

    for token in TOKENS:
        assert token in light, token
    for step in (50, 100, 200, 300, 400, 500, 600, 700, 750, 800, 850, 900, 950):
        assert f"gray-{step}" in light, step
    assert "color-scheme: light" in CSS and "color-scheme: dark" in CSS


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("fill", ["ok", "fail", "needs", "voice", "ink"])
def test_text_on_solid_fills_meets_wcag_aa(theme, fill):
    """`text-ground` is used on solid state fills (e.g. a bg-fail button)."""
    palette = _dark() if theme == "dark" else _light()

    ratio = _contrast(palette["ground"], palette[fill])
    assert ratio >= 4.5, f"{theme}: ground on {fill} is {ratio:.2f}"


def test_no_raw_colour_values_in_templates():
    """Colours in inline styles and <style> blocks must use the tokens too."""
    pattern = re.compile(
        r"(?:color|background|fill|stroke|border)[\w-]*\s*:\s*[^;\"'{}]*"
        r"(?:#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\()"
    )
    offenders = [
        f"{p.relative_to(WEB)}: {m.group(0)}"
        for p in (WEB / "templates").rglob("*.html")
        for m in pattern.finditer(p.read_text())
    ]
    assert offenders == []


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("fg", TEXT_TOKENS)
def test_text_tokens_meet_wcag_aa(theme, fg):
    palette = _dark() if theme == "dark" else _light()

    for bg in BACKGROUNDS:
        ratio = _contrast(palette[fg], palette[bg])
        assert ratio >= 4.5, f"{theme}: {fg} on {bg} is {ratio:.2f}"


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_primary_button_text_contrast(theme):
    palette = _dark() if theme == "dark" else _light()

    assert _contrast(palette["ground"], palette["ink"]) >= 7


def test_no_hard_coded_hue_classes_remain():
    pattern = re.compile(
        r"\b(?:bg|text|border|ring|divide)-(?:white|indigo|blue|purple|violet|green|emerald|"
        r"red|rose|amber|yellow|orange|cyan|sky|teal)(?:-\d{2,3})?\b"
    )
    sources = [
        *(WEB / "templates").rglob("*.html"),
        WEB / "zebra_agent_web" / "api" / "templatetags" / "form_tags.py",
        WEB / "zebra_agent_web" / "api" / "web_views.py",
    ]
    offenders = {
        str(p.relative_to(WEB)): sorted(set(pattern.findall(p.read_text())))
        for p in sources
        if pattern.search(p.read_text())
    }
    assert offenders == {}


def test_compat_layer_removed():
    assert "Temporary: remove in the sweep" not in CSS
    assert "var(--color-gray-200, currentColor)" not in CSS


def test_diagram_colours_follow_the_theme():
    from zebra_agent_web.diagram import COLORS

    assert all(value.startswith("var(--color-") for value in COLORS.values())
