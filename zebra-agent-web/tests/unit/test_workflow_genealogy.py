"""The private genealogy page (#238)."""

import re
from urllib.parse import parse_qs

import pytest
from zebra_agent.library import WorkflowLibrary
from zebra_agent.provenance import content_sha256
from zebra_agent_web.api import web_views
from zebra_agent_web.api.genealogy_view import diff_lines, genealogy_svg

pytestmark = [pytest.mark.django_db(transaction=True)]

_YAML = """name: "Old Search"
description: "Searches the web"
tags: ["web"]
first_task: a
tasks:
  a:
    name: A
    action: llm_call
    properties:
      prompt: "search {{goal}}"
routings: []
"""
V2 = _YAML.replace("search {{goal}}", "search carefully {{goal}}")
V3 = _YAML.replace("search {{goal}}", "search carefully and cite {{goal}}")


@pytest.fixture
def library(tmp_path, monkeypatch):
    import zebra_agent_web.api.agent_engine as agent_engine_module

    library = WorkflowLibrary(tmp_path / "workflows", owner_user_id=1, sphere="home")

    async def _noop():
        return None

    monkeypatch.setattr(agent_engine_module, "ensure_initialized", _noop)
    monkeypatch.setattr(agent_engine_module, "get_library", lambda: library)
    return library


@pytest.fixture
def rf(db):
    from django.contrib.auth import get_user_model
    from django.test import RequestFactory
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")
    user = get_user_model().objects.create_user(username="genealogy-user")

    def _make(path):
        request = RequestFactory().get(path)
        request.user = user
        return request

    return _make


async def _page(rf, name="Old Search") -> tuple[int, str]:
    response = await web_views.workflow_genealogy(rf(f"/workflows/{name}/genealogy/"), name)
    return response.status_code, response.content.decode()


async def test_two_optimizations_render_three_versions_two_diffs_and_reasons(library, rf):
    library.add_workflow(_YAML)
    library.save(
        V2,
        writer="optimizer",
        reason={"text": "three failed runs at work", "source": "evaluator"},
    )
    library.save(
        V3,
        writer="creator",
        reason={"text": "I kept forgetting sources.", "kind": "voice", "source": "selector"},
    )

    status, html = await _page(rf)

    assert status == 200
    assert html.count('data-version="') == 3
    assert html.count('data-testid="diff"') == 2
    assert "three failed runs at work" in html
    assert "I kept forgetting sources." in html
    assert "Dream cycle evaluation" in html and "Workflow choice" in html
    # Recorded reasoning is labelled; the voice line is not.
    assert html.count("recorded reasoning") == 1
    assert "Nothing shared yet" in html and "No forks waiting" in html
    assert 'role="img"' in html
    for key in (content_sha256(y) for y in (_YAML, V2, V3)):
        assert f'href="#v-{key[:12]}"' in html and f'id="v-{key[:12]}"' in html
    assert "<script" not in html.split('data-testid="genealogy-graph"')[1].split("</main>")[0]


async def test_no_reason_recorded_and_unknown_legacy_writer(library, rf):
    library.ensure_initialized()
    (library.library_path / "old_search.yaml").write_text(_YAML)  # pre-#229 file
    library.save(V2, writer="human")

    _, html = await _page(rf)

    writers = re.findall(r'data-testid="writer">([^<]+)<', html)
    assert writers == ["human", "unknown"]
    assert "No reason recorded." in html
    assert "(file date)" in html
    assert "Written before provenance was recorded" in html


async def test_retired_and_hash_only_versions_are_labelled(library, rf):
    library.add_workflow(_YAML)
    library.save(V2, writer="optimizer")
    library.save(V3, writer="optimizer")
    v2_file = next(
        p for p in library.library_path.glob("*.yaml") if "carefully {{goal}}" in p.read_text()
    )
    library.retire("Old Search", "superseded", path=v2_file)
    (library.library_path / "old_search.yaml").unlink()  # the first version is gone

    _, html = await _page(rf)

    assert "no file on this device" in html
    assert 'data-testid="retired"' in html and "superseded" in html
    assert "known only by hash" in html


async def test_unknown_workflow_is_404(library, rf):
    status, _ = await _page(rf, "Missing")
    assert status == 404


def _prod_middleware() -> list[str]:
    """The MIDDLEWARE declared in settings.py, read from source.

    ``test_settings`` removes ``LoginRequiredMiddleware`` from the shared list object, so the
    imported value cannot be trusted. Reading the source means dropping the middleware from
    ``settings.py`` fails the login test below. ``SetupRedirectMiddleware`` is left out: it only
    handles first-run setup and causes SQLite lock contention in unit tests.
    """
    import ast
    from pathlib import Path

    import zebra_agent_web.settings as prod_settings

    tree = ast.parse(Path(prod_settings.__file__).read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "MIDDLEWARE" for t in node.targets
        ):
            stack = ast.literal_eval(node.value)
            return [m for m in stack if not m.endswith("SetupRedirectMiddleware")]
    raise AssertionError("settings.py declares no MIDDLEWARE list")


@pytest.mark.parametrize(
    ("path", "marker"),
    [
        ("/workflows/Old%20Search/genealogy/", 'data-testid="genealogy-graph"'),
        ("/commons/", "Commons"),
    ],
)
def test_pages_are_behind_login(library, settings, tmp_path, path, marker):
    """With the prod middleware stack, anonymous visitors go to login; the owner gets the page.

    Fails if the view is made login-exempt or LoginRequiredMiddleware leaves settings.py (#274).
    """
    from django.contrib.auth import get_user_model
    from django.test import Client
    from zebra_agent_web.api.identity import set_identity_sync

    settings.MIDDLEWARE = _prod_middleware()
    settings.ZEBRA_AGENT_SETTINGS = {
        **settings.ZEBRA_AGENT_SETTINGS,
        "COMMONS_ENABLED": True,
        "COMMONS_KEY_DIR": str(tmp_path / "keys"),
    }
    set_identity_sync("Test User")
    library.add_workflow(_YAML)

    anonymous = Client().get(path)
    assert anonymous.status_code == 302
    login, _, query = anonymous.url.partition("?")
    assert login == settings.LOGIN_URL
    assert parse_qs(query)["next"] == [path]

    client = Client()
    client.force_login(get_user_model().objects.create_user(username="login-owner"))
    response = client.get(path)
    assert response.status_code == 200
    assert marker in response.content.decode()


async def test_detail_page_links_to_the_genealogy(library, rf, monkeypatch):
    import zebra_agent_web.api.agent_engine as agent_engine_module
    from zebra_agent.metrics import WorkflowStats

    class _Metrics:
        async def get_stats(self, name):
            return WorkflowStats(workflow_name=name)

    monkeypatch.setattr(agent_engine_module, "get_metrics", lambda: _Metrics())
    library.add_workflow(_YAML)
    response = await web_views.workflow_detail(rf("/workflows/Old Search/"), "Old Search")
    assert 'href="/workflows/Old%20Search/genealogy/"' in response.content.decode()


def test_svg_uses_theme_tokens_only(tmp_path):
    from zebra_agent.genealogy import build_genealogy

    library = WorkflowLibrary(tmp_path / "wf")
    library.add_workflow(_YAML)
    library.save(V2, writer="optimizer")
    svg = genealogy_svg(build_genealogy(library, "Old Search"))
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b(?![\w-])", svg.replace('href="#v-', ""))
    assert "var(--color-ok)" in svg  # the current version


def test_diff_lines_drop_file_headers():
    lines = diff_lines("--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new\n same")
    assert [(line.kind, line.text) for line in lines] == [
        ("hunk", "@@ -1 +1 @@"),
        ("remove", "-old"),
        ("add", "+new"),
        ("context", " same"),
    ]
