"""Tests for the web UI foundation (#159): icon tag, vendored assets, no CDN."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import RequestFactory
from zebra_agent_web.api.templatetags import icon_tags
from zebra_agent_web.api.templatetags.icon_tags import ICON_DIR

WEB_DIR = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


def _render(source: str, **context) -> str:
    return Template("{% load icon_tags %}" + source).render(Context(context))


def _template_sources() -> dict[Path, str]:
    return {p: p.read_text() for p in TEMPLATE_DIR.rglob("*.html")}


# ---------------------------------------------------------------------------
# {% icon %} tag
# ---------------------------------------------------------------------------


def test_icon_renders_inline_svg_with_attributes():
    html = _render('{% icon "moon" class="h-5 w-5" %}')

    assert html.startswith("<svg")
    assert 'class="h-5 w-5"' in html
    assert 'aria-hidden="true"' in html
    assert 'fill="currentColor"' in html
    assert html.count("<svg") == 1


def test_icon_name_can_come_from_a_variable():
    html = _render('{% icon name class="x" %}', name="shield-check")

    assert html.startswith("<svg")


def test_icon_escapes_attribute_values():
    html = _render('{% icon "moon" title=t %}', t='"><script>')

    assert "<script>" not in html
    assert "&quot;&gt;&lt;script&gt;" in html


@pytest.mark.parametrize("name", ["no-such-icon", "../icon_tags", "Moon", ""])
def test_unknown_or_invalid_icon_renders_nothing_and_logs(name):
    # The project logging config stops propagation, so watch the module logger directly.
    with patch.object(icon_tags.logger, "error") as log_error:
        html = _render("{% icon name %}", name=name)

    assert html == ""
    log_error.assert_called_once()
    assert "Unknown icon" in log_error.call_args.args[0]


def test_every_icon_used_in_templates_is_vendored():
    used: set[str] = set()
    for source in _template_sources().values():
        used.update(re.findall(r'{%\s*icon\s+"([a-z0-9-]+)"', source))
        # Names passed to the nav and stat-card partials.
        for include in re.findall(
            r"{%\s*include\s+\"(?:partials/nav_item|components/stat_card)"
            r"\.html\"[^%]*%}",
            source,
        ):
            used.update(re.findall(r'icon="([a-z0-9-]+)"', include))

    assert used, "expected templates to use icons"
    missing = sorted(n for n in used if not (ICON_DIR / f"{n}.svg").is_file())
    assert missing == []


def test_phosphor_licence_is_vendored_with_icons():
    assert (ICON_DIR / "LICENSE").read_text().startswith("MIT License")


# ---------------------------------------------------------------------------
# Base layout
# ---------------------------------------------------------------------------


@pytest.fixture
def staff_user(db):
    return get_user_model().objects.create_user(username="staff", is_staff=True)


def _render_base(user) -> str:
    request = RequestFactory().get("/")
    request.user = user
    return render_to_string("base.html", {"user": user}, request=request)


def test_every_nav_item_has_an_icon(staff_user):
    html = _render_base(staff_user)
    nav = html.split("<nav", 1)[1].split("</nav>", 1)[0]
    links = re.findall(r"<a href=.*?</a>", nav, flags=re.S)

    labels = [re.sub(r"<[^>]+>|\s+", " ", link).strip() for link in links]
    assert "Knowledge" in labels and "Trust" in labels and "Ethics Audit" in labels
    for link, label in zip(links, labels, strict=True):
        assert "<svg" in link, f"nav item {label!r} has no icon"


def test_base_links_compiled_stylesheet_and_vendored_scripts(staff_user):
    html = _render_base(staff_user)

    assert 'href="/static/css/app.css"' in html
    assert 'src="/static/vendor/htmx-2.0.4.min.js"' in html
    assert 'src="/static/vendor/alpine-3.17.4.min.js"' in html


def test_no_template_loads_assets_from_a_cdn():
    offenders = [
        str(path.relative_to(WEB_DIR))
        for path, source in _template_sources().items()
        if re.search(r"cdn\.tailwindcss\.com|unpkg\.com|cdn\.jsdelivr\.net", source)
    ]
    assert offenders == []


def test_vendored_static_files_exist():
    for rel in (
        "vendor/htmx-2.0.4.min.js",
        "vendor/alpine-3.17.4.min.js",
        "fonts/geist-latin-wght-normal.woff2",
        "fonts/geist-mono-latin-wght-normal.woff2",
        "fonts/OFL.txt",
        "css/src/app.css",
    ):
        assert (STATIC_DIR / rel).is_file(), rel


def test_stylesheet_source_defines_design_tokens():
    source = (STATIC_DIR / "css" / "src" / "app.css").read_text()

    for token in (
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
    ):
        assert f"--color-{token}:" in source, token
    assert '--font-sans: "Geist"' in source
    assert '--font-mono: "Geist Mono"' in source


def test_stat_card_has_no_dynamic_class_names():
    source = (TEMPLATE_DIR / "components" / "stat_card.html").read_text()

    assert not re.search(r"-\{\{", source)
