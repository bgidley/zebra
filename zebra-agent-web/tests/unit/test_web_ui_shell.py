"""Tests for the web UI shell (#160): nav, needs-you badge, bare layout, components."""

from __future__ import annotations

import html as html_lib
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import RequestFactory
from zebra.core.models import (
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    TaskDefinition,
    TaskInstance,
    TaskState,
)
from zebra.storage.memory import InMemoryStore
from zebra_agent_web.api import engine

APP_CSS = Path(__file__).resolve().parents[2] / "static" / "css" / "src" / "app.css"


def _render_page(template: str, user, path: str = "/") -> str:
    request = RequestFactory().get(path)
    request.user = user
    return render_to_string(template, {"user": user}, request=request)


@pytest.fixture
def staff_user(db):
    return get_user_model().objects.create_user(username="staff", is_staff=True)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def _nav(html: str) -> str:
    return html.split("<nav", 1)[1].split("</nav>", 1)[0]


def test_nav_groups_render_in_order(staff_user):
    nav = _nav(_render_page("base.html", staff_user))
    text = re.sub(r"<[^>]+>|\s+", " ", nav)

    order = [
        "Dashboard",
        "Tasks",
        "Run Goal",
        "Activity",
        "Agent",
        "Workflows",
        "Knowledge",
        "Dream Cycles",
        "Governance",
        "Trust",
        "Values Tags",
        "Ethics Audit",
    ]
    positions = [text.index(f" {label} ") for label in order]
    assert positions == sorted(positions)


def test_ethics_audit_hidden_from_non_staff(db):
    user = get_user_model().objects.create_user(username="plain")

    assert "Ethics Audit" not in _nav(_render_page("base.html", user))


def test_tasks_item_loads_needs_you_badge_lazily(staff_user):
    nav = _nav(_render_page("base.html", staff_user))
    tasks_link = re.search(r'<a href="/tasks/".*?</a>', nav, flags=re.S).group(0)

    assert 'hx-get="/nav/needs-you/"' in tasks_link
    assert 'hx-trigger="load"' in tasks_link


def test_active_nav_item_is_marked_current(staff_user):
    nav = _nav(_render_page("base.html", staff_user, path="/knowledge/"))
    current = re.findall(r'<a href="([^"]+)"[^>]*aria-current="page"', nav, flags=re.S)

    assert current == ["/knowledge/"]


def test_version_info_lives_in_sidebar_not_a_fixed_strip(staff_user):
    html = _render_page("base.html", staff_user)
    aside = html.split("<aside", 1)[1].split("</aside>", 1)[0]

    assert 'data-testid="version-info"' in aside
    assert html.count('data-testid="version-info"') == 1
    assert "fixed bottom-0" not in html
    # Each commit row shows hash, date and subject (version-footer spec).
    for field in ('x-text="c.hash"', 'x-text="c.date"', 'x-text="c.subject"'):
        assert field in aside


def test_sidebar_is_hidden_by_css_before_alpine_runs(staff_user):
    """#166: on iPad the sidebar flashed over the page until deferred Alpine ran,
    because only an Alpine-bound class hid it. It must be hidden by CSS alone."""
    html = _render_page("base.html", staff_user)
    aside_tag = re.search(r"<aside[^>]*>", html, flags=re.S).group(0)

    assert "app-sidebar" in aside_tag
    assert 'data-open="false"' in aside_tag
    assert "translate-x" not in aside_tag

    css = APP_CSS.read_text()
    rule = re.search(r"@media \(max-width: 63\.999rem\) \{(.*?)\n  \}", css, flags=re.S).group(1)
    assert re.search(r"\.app-sidebar \{\s*translate: -100% 0;", rule)
    assert re.search(r'\.app-sidebar\[data-open="true"\] \{\s*translate: 0 0;', rule)


def test_menu_button_controls_sidebar_and_locks_scroll(staff_user):
    html = _render_page("base.html", staff_user)

    assert 'aria-controls="app-sidebar"' in html
    assert "classList.toggle('overflow-hidden', sidebarOpen)" in html
    # Rotating to landscape (lg) with the menu open must release the scroll lock.
    assert "@resize.window=\"if (window.matchMedia('(min-width: 64rem)').matches)" in html


def _top_bar(page: str) -> str:
    return page.split('data-testid="mobile-top-bar"', 1)[1].split("<main", 1)[0]


def test_mobile_top_bar_has_single_primary_action(staff_user):
    top_bar = _top_bar(_render_page("base.html", staff_user, path="/activity/"))

    assert 'aria-label="Open navigation"' in top_bar
    assert top_bar.count("btn-primary") == 1
    assert 'href="/run/"' in top_bar


def test_mobile_top_bar_omits_run_goal_on_run_page(staff_user):
    top_bar = _top_bar(_render_page("base.html", staff_user, path="/run/"))

    assert "btn-primary" not in top_bar


# ---------------------------------------------------------------------------
# Needs-you badge
# ---------------------------------------------------------------------------


def _definition(def_id: str, tasks: dict[str, bool]) -> ProcessDefinition:
    return ProcessDefinition(
        id=def_id,
        name=def_id,
        first_task_id=next(iter(tasks)),
        tasks={tid: TaskDefinition(id=tid, name=tid, auto=auto) for tid, auto in tasks.items()},
    )


async def _goal(store, pid: str, task_state: TaskState, human: bool) -> None:
    await store.save_process(
        ProcessInstance(
            id=pid,
            definition_id="wf",
            state=ProcessState.RUNNING,
            properties={"goal": pid},
            created_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    await store.save_task(
        TaskInstance(
            id=f"{pid}-t",
            process_id=pid,
            task_definition_id="ask" if human else "work",
            state=task_state,
            foe_id="f",
        )
    )


@pytest.fixture
def completed_setup(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
async def stub_store(monkeypatch, completed_setup):
    store = InMemoryStore()
    await store.save_definition(_definition("wf", {"work": True, "ask": False}))

    async def _noop():
        return None

    monkeypatch.setattr(engine, "ensure_initialized", _noop)
    monkeypatch.setattr(engine, "get_store", lambda: store)
    return store


@pytest.mark.django_db(transaction=True)
async def test_needs_you_counts_goals_waiting_on_a_human(authenticated_async_client, stub_store):
    await _goal(stub_store, "a", TaskState.READY, human=True)
    await _goal(stub_store, "b", TaskState.READY, human=True)
    await _goal(stub_store, "c", TaskState.RUNNING, human=False)

    response = await authenticated_async_client.get("/nav/needs-you/")

    assert response.status_code == 200
    badge = response.content.decode()
    assert 'id="nav-needs-you"' in badge
    assert re.search(r">\s*2\s*</span>", badge)
    assert 'aria-label="2 waiting on you"' in badge


@pytest.mark.django_db(transaction=True)
async def test_needs_you_is_empty_when_nothing_waits(authenticated_async_client, stub_store):
    await _goal(stub_store, "c", TaskState.RUNNING, human=False)

    response = await authenticated_async_client.get("/nav/needs-you/")

    assert response.status_code == 200
    assert re.search(r'id="nav-needs-you"[^>]*></span>', response.content.decode())


@pytest.mark.django_db(transaction=True)
async def test_needs_you_store_failure_returns_empty_badge(
    authenticated_async_client, completed_setup, monkeypatch
):
    async def _boom():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(engine, "ensure_initialized", _boom)

    response = await authenticated_async_client.get("/nav/needs-you/")

    assert response.status_code == 200
    assert re.search(r'id="nav-needs-you"[^>]*></span>', response.content.decode())


class _StubLibrary:
    async def list_workflows(self):
        return []


class _StubMetrics:
    async def get_all_stats(self):
        return []

    async def get_recent_runs(self, limit=10):
        return []


@pytest.fixture
def stub_dashboard(monkeypatch, stub_store):
    from zebra_agent_web.api import agent_engine

    async def _noop():
        return None

    def _not_ready():
        raise RuntimeError("not initialized in tests")

    monkeypatch.setattr(agent_engine, "ensure_initialized", _noop)
    monkeypatch.setattr(agent_engine, "get_library", lambda: _StubLibrary())
    monkeypatch.setattr(agent_engine, "get_metrics", lambda: _StubMetrics())
    monkeypatch.setattr(agent_engine, "get_budget_manager", _not_ready)
    monkeypatch.setattr(agent_engine, "get_trust", _not_ready)


@pytest.mark.django_db(transaction=True)
async def test_async_page_shows_staff_nav_and_signed_in_user(async_client, stub_dashboard):
    """Regression: `user` was never in the template context, so the staff-only
    Ethics Audit link and the signed-in user footer never rendered."""
    staff = await get_user_model().objects.acreate(username="ada", is_staff=True)
    await async_client.aforce_login(staff)

    response = await async_client.get("/")

    assert response.status_code == 200
    page = response.content.decode()
    assert 'href="/ethics-audit/"' in _nav(page)
    aside = page.split("<aside", 1)[1].split("</aside>", 1)[0]
    assert 'aria-label="Sign out"' in aside


@pytest.mark.django_db(transaction=True)
async def test_async_page_hides_ethics_audit_from_non_staff(async_client, stub_dashboard):
    user = await get_user_model().objects.acreate(username="bob")
    await async_client.aforce_login(user)

    response = await async_client.get("/")

    assert response.status_code == 200
    assert 'href="/ethics-audit/"' not in _nav(response.content.decode())


# ---------------------------------------------------------------------------
# Bare layout
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("path", ["/auth/login/", "/auth/setup/"])
async def test_signed_out_routes_serve_bare_layout(async_client, path):
    response = await async_client.get(path)

    assert response.status_code == 200
    page = response.content.decode()
    assert "<nav" not in page
    assert "zebra-mark" in page
    assert 'data-testid="version-info"' in page


@pytest.mark.parametrize(
    "template", ["pages/auth_login.html", "pages/auth_setup.html", "pages/setup.html"]
)
def test_signed_out_pages_use_bare_layout_without_nav(db, template):
    html = _render_page(template, AnonymousUser(), path="/auth/login/")

    assert "<nav" not in html
    assert "zebra-mark" in html
    assert 'data-testid="version-info"' in html
    assert 'href="/static/css/app.css"' in html


def test_sign_in_page_keeps_webauthn_hooks(db):
    html = _render_page("pages/auth_login.html", AnonymousUser(), path="/auth/login/")

    for hook in ('id="signin-btn"', 'id="login-error"', "/static/js/webauthn.js"):
        assert hook in html


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------


def _render(source: str, **context) -> str:
    return Template(source).render(Context(context)).strip()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1234.5, "$1,234.50"),
        ("0.004", "<$0.01"),
        (0, "$0.00"),
        (None, ""),
        ("", ""),
        ("not a number", ""),
        (-3.2, "-$3.20"),
        (0.01, "$0.01"),
    ],
)
def test_usd_filter(value, expected):
    # Autoescaped in HTML ("&lt;$0.01"); the browser shows the unescaped text.
    rendered = _render("{% load format_tags %}{{ v|usd }}", v=value)
    assert html_lib.unescape(rendered) == expected


@pytest.mark.parametrize(
    ("confidence", "variant"),
    [
        (1.0, "certainty-full"),
        (0.8, "certainty-high"),
        (0.6, "certainty-medium"),
        (0.3, "certainty-low"),
    ],
)
def test_certainty_stripe_variants(confidence, variant):
    html = _render('{% include "components/certainty.html" %}', confidence=confidence)

    assert variant in html
    assert f'aria-label="confidence {confidence:.2f}"' in html


@pytest.mark.parametrize(
    ("state", "css", "label"),
    [
        ("running", "state-dot-running", "running"),
        ("ok", "state-dot-ok", "succeeded"),
        ("fail", "state-dot-fail", "failed"),
        ("needs", "state-dot-needs", "waiting on you"),
    ],
)
def test_state_dot_variants(state, css, label):
    html = _render('{% include "components/state_dot.html" %}', state=state)

    assert css in html
    assert f'aria-label="{label}"' in html


def test_gray_scale_is_remapped_to_the_neutral_frame():
    source = APP_CSS.read_text()

    for step in (50, 100, 200, 300, 400, 500, 600, 700, 750, 800, 850, 900, 950):
        assert re.search(rf"--color-gray-{step}:\s*#[0-9a-f]{{6}};", source), step
    ground = re.search(r"--color-ground:\s*(#[0-9a-f]{6});", source).group(1)
    assert re.search(r"--color-gray-950:\s*(#[0-9a-f]{6});", source).group(1) == ground


def test_shared_component_classes_are_defined():
    source = APP_CSS.read_text()

    for cls in (
        ".btn {",
        ".btn-primary {",
        ".btn-quiet {",
        ".btn-danger {",
        ".panel {",
        ".state-dot {",
        ".certainty {",
        ".zebra-mark {",
    ):
        assert cls in source, cls
