"""``contribute_diff_scan`` (#282 slice A): added lines only, rules plus one LLM, fails closed.

Every rule has a known-bad diff. Secrets are assembled at runtime so this file does not
itself trip secret scanners.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from zebra_tasks.contribute.diff_scan import (
    ROUTE_CLEAN,
    ROUTE_REJECTED,
    ContributeDiffScanAction,
    DiffParseError,
    blocked_reason,
    noreply_email,
    parse_diff,
    scan_diff,
    shannon_entropy,
)
from zebra_tasks.llm.base import LLMResponse, TokenUsage
from zebra_tasks.llm.client import set_llm_factory

REPO = Path(__file__).resolve().parents[2]
CLEAN_REPLY = '{"personal_data": false, "findings": []}'


def _response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=None,
        finish_reason="stop",
        usage=TokenUsage(input_tokens=10, output_tokens=20),
        model="test-model",
    )


def _llm(*contents: str) -> MagicMock:
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=[_response(c) for c in contents])
    return provider


def added(path: str, *lines: str, new: bool = False) -> str:
    """A git diff adding *lines* to *path* (after one context line, unless new)."""
    if new:
        header = f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n"
        body = f"+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n"
        return header + body + "".join(f"+{line}\n" for line in lines)
    header = f"diff --git a/{path} b/{path}\nindex 1111111..2222222 100644\n--- a/{path}\n"
    body = f"+++ b/{path}\n@@ -1,1 +1,{len(lines) + 1} @@\n import os\n"
    return header + body + "".join(f"+{line}\n" for line in lines)


async def _scan(diff, reply=CLEAN_REPLY, **kwargs):
    llm = _llm(reply, reply) if reply is not None else None
    result = await scan_diff(diff, llm=llm, **kwargs)
    json.dumps(result)  # JSON-serialisable: it is stored as a process property
    return result, llm


def _payload(llm) -> str:
    """The user message the LLM was shown."""
    call = llm.complete.call_args
    messages = call.kwargs.get("messages") or call.args[0]
    return messages[1].content


def _kinds(result) -> set[str]:
    return {f["kind"] for f in result["findings"]}


# Built at runtime: secret formats as a scanner (or GitHub push protection) would see them.
GH_TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
GH_PAT = "github_pat_" + "11ABCDEFG0" + "abcdefghijklmnopqrstuvwxyz0123456789"
OPENROUTER = "sk-or-" + "v1-" + "0123456789abcdef0123456789abcdef"
ANTHROPIC = "sk-ant-" + "api03-" + "AbCdEf0123456789AbCdEf0123456789"
NSEC = "nsec1" + "qypqxpq9qtpqscx7peytzfwtdjmcv0mrz5rjpej8vjppfkqfqy8skqfv3l"
PEM = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
CERT = "-----BEGIN " + "CERTIFICATE-----"
OCID_USER = "ocid1." + "user.oc1..aaaaaaaab3k2examplexyz"
OCID_TENANCY = "ocid1." + "tenancy.oc1..aaaaaaaaq3exampleabc"
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
AWS_SECRET = "aws_secret_access_key" + " = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
JWT = (
    "eyJ"
    + "hbGciOiJIUzI1NiJ9.eyJ"
    + "zdWIiOiIxMjM0NTY3ODkwIn0."
    + "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9P"
)
ENTROPY = "Zx9" + "Qm4Lr7Tb2Wc8Yh5Kd3Nf6Pj1Gs0Va"  # 32 random-looking characters
QUOTED = 'DB_PASSWORD = "' + 'hunter2hunter2"'


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        (f'TOKEN = "{GH_TOKEN}"', "secret"),
        (f"token: {GH_PAT}", "secret"),
        (f"key = '{OPENROUTER}'", "secret"),
        (f"ANTHROPIC_API_KEY={ANTHROPIC}", "secret"),
        (f"zebra_key = '{NSEC}'", "secret"),
        (PEM, "secret"),
        (CERT, "secret"),
        (f"user = '{OCID_USER}'", "secret"),
        (f"tenancy = '{OCID_TENANCY}'", "secret"),
        (f"aws_access_key_id = {AWS_KEY}", "secret"),
        (AWS_SECRET, "secret"),
        (f"Authorization: {JWT}", "secret"),
        (f"seed = '{ENTROPY}'", "high_entropy"),
        (QUOTED, "secret"),
        ("url = 'https://admin:s3cretpw@db.example.org/x'", "url_credentials"),
        ("# ask jane.smith@gmail.com about this", "email"),
        ("# call +44 7700 900123 first", "phone"),
        ("# lives at SW1A 1AA", "postcode"),
        ("# card 4111 1111 1111 1111", "card_number"),
        ("# NI number AB 12 34 56 C", "ni_number"),
        ("HOST = 'build01.corp'", "internal_host"),
        ("BASE = 'http://nas.local:8080/api'", "internal_host"),
        ("PEER = '10.1.2.3'", "internal_host"),
        ("# Project: Bluebird migration", "codename"),
        ("# built for the customer Initech", "customer"),
    ],
)
async def test_each_rule_rejects_an_added_line(line, kind):
    result, llm = await _scan(added("zebra-tasks/zebra_tasks/x.py", line))
    assert result["verdict"] == ROUTE_REJECTED and not result["clean"]
    assert not result["failed_closed"]
    assert kind in _kinds(result)
    hit = next(f for f in result["findings"] if f["kind"] == kind)
    assert hit["path"] == "zebra-tasks/zebra_tasks/x.py:2"
    # Masked: never more than two characters of the match
    assert "…" in hit["text"]
    assert line[5:] not in json.dumps(result["findings"])
    llm.complete.assert_not_called()  # rules reject before the LLM sees anything


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        (".env", "environment file"),
        ("deploy/podman/.env.prod", "environment file"),
        ("deploy/site.env", "environment file"),
        ("certs/server.pem", "key or certificate file"),
        ("keys/signing.key", "key or certificate file"),
        ("home/.ssh/config", "credential directory"),
        (".aws/config", "credential directory"),
        (".oci/config", "credential directory"),
        ("commons-keys/zebra.json", "credential directory"),
        ("id_ed25519", "credential file"),
        (".netrc", "credential file"),
        ("build/libzebra.so", "binary file"),
        ("db.sqlite3", "binary file"),
    ],
)
async def test_blocked_files_reject(path, reason):
    assert blocked_reason(path) == reason
    result, _ = await _scan(added(path, "harmless = 1", new=True))
    assert result["verdict"] == ROUTE_REJECTED
    assert {"source": "rule", "kind": "blocked_file", "path": path, "reason": reason} in result[
        "findings"
    ]


async def test_binary_patch_is_blocked():
    diff = (
        "diff --git a/docs/logo.png b/docs/logo.png\nnew file mode 100644\n"
        "index 0000000..1234567\nBinary files /dev/null and b/docs/logo.png differ\n"
    )
    result, _ = await _scan(diff)
    assert result["verdict"] == ROUTE_REJECTED
    assert result["findings"][0]["reason"] == "binary file"


async def test_git_binary_patch_is_blocked():
    diff = (
        "diff --git a/a.dat b/a.dat\nnew file mode 100644\nindex 0000000..1234567\n"
        "GIT binary patch\nliteral 4\nLcmZQzWMT!K00031\n\nliteral 0\nHcmV?d00001\n"
    )
    result, _ = await _scan(diff)
    assert "blocked_file" in _kinds(result)


async def test_confidential_patterns_apply():
    diff = added("README.md", "Deployed for Zorblax Holdings")
    result, _ = await _scan(diff, patterns=["zorblax"])
    assert "confidential_pattern" in _kinds(result)


async def test_confidential_env_patterns_apply_through_the_action(monkeypatch):
    monkeypatch.setenv("ZEBRA_SYNC_CONFIDENTIAL_PATTERNS", "zorblax;;other")
    result, _ = await _run_action({"diff": added("README.md", "Zorblax rollout")})
    assert "confidential_pattern" in _kinds(result.output)


# --- added content only ---------------------------------------------------------------


async def test_removed_and_context_lines_do_not_count():
    diff = (
        "diff --git a/app.py b/app.py\nindex 1111111..2222222 100644\n--- a/app.py\n+++ b/app.py\n"
        f"@@ -1,3 +1,3 @@\n # {GH_TOKEN} was here\n-TOKEN = '{GH_TOKEN}'\n"
        "+TOKEN = os.environ['TOKEN']\n x = 1\n"
    )
    result, _ = await _scan(diff)
    assert result["verdict"] == ROUTE_CLEAN, result
    assert result["added_lines"] == 1


async def test_deleted_secret_file_does_not_count():
    diff = (
        "diff --git a/.env b/.env\ndeleted file mode 100644\nindex 1111111..0000000\n"
        f"--- a/.env\n+++ /dev/null\n@@ -1,1 +0,0 @@\n-GITHUB_TOKEN={GH_TOKEN}\n"
    )
    result, _ = await _scan(diff)
    assert result["verdict"] == ROUTE_CLEAN, result


async def test_added_line_that_looks_like_a_header_is_still_content():
    # Hunk counts decide: "++ token" is an added line whose text starts with "++".
    diff = (
        "diff --git a/notes.md b/notes.md\nindex 1..2 100644\n--- a/notes.md\n+++ b/notes.md\n"
        f"@@ -1,0 +1,2 @@\n+++ {GH_TOKEN}\n+--- {AWS_KEY}\n"
    )
    result, _ = await _scan(diff)
    assert result["verdict"] == ROUTE_REJECTED
    assert {f["path"] for f in result["findings"]} == {"notes.md:1", "notes.md:2"}


@pytest.mark.parametrize("where", ["commit_messages", "pr_title", "pr_body", "author_name"])
async def test_secret_in_metadata_rejects(where):
    result, _ = await _scan(added("a.py", "x = 1"), **{where: f"see {GH_TOKEN}"})
    assert result["verdict"] == ROUTE_REJECTED
    assert "secret" in _kinds(result)


async def test_secret_in_a_path_rejects():
    result, _ = await _scan(added(f"docs/{GH_TOKEN}.md", "hello", new=True))
    assert "secret" in _kinds(result)
    assert any(f["path"].endswith("(path)") for f in result["findings"])


async def test_text_outside_hunks_is_scanned():
    diff = f"From: someone\nSubject: [PATCH] key {GH_TOKEN}\n\n" + added("a.py", "x = 1")
    result, _ = await _scan(diff)
    assert "secret" in _kinds(result)


async def test_rename_scans_both_paths():
    diff = (
        "diff --git a/old.py b/jane.doe@gmail.com.py\nsimilarity index 100%\n"
        "rename from old.py\nrename to jane.doe@gmail.com.py\n"
    )
    result, _ = await _scan(diff)
    assert "email" in _kinds(result)


async def test_noreply_trailers_are_allowed():
    msg = (
        "fix: thing\n\nSigned-off-by: Octo Cat <42+octo@users.noreply.github.com>\n"
        "Co-Authored-By: Claude <noreply@anthropic.com>\n"
        "Claude-Session: https://claude.ai/code/session_01G2od46UdwGJxMY8ZgRqVkn\n"
    )
    result, _ = await _scan(added("a.py", "x = 1"), commit_messages=[msg])
    assert result["verdict"] == ROUTE_CLEAN, result["findings"]


async def test_author_email_scanned_when_not_rewritten():
    result, _ = await _scan(added("a.py", "x = 1"), author_email="jane.smith@gmail.com")
    assert "email" in _kinds(result)
    assert result["author_email"] is None


async def test_author_email_rewritten_to_noreply():
    result, _ = await _scan(
        added("a.py", "x = 1"),
        author_email="jane.smith@gmail.com",
        github_login="octo-cat",
        github_user_id=42,
    )
    assert result["verdict"] == ROUTE_CLEAN
    assert result["author_email"] == "42+octo-cat@users.noreply.github.com"


def test_noreply_email():
    assert noreply_email("octo") == "octo@users.noreply.github.com"
    assert noreply_email("octo", "42") == "42+octo@users.noreply.github.com"
    assert noreply_email("bad login!") is None
    assert noreply_email("-octo") is None
    assert noreply_email(None) is None


def test_entropy_rule_spares_hashes_and_identifiers():
    assert shannon_entropy("aaaa") == 0.0
    assert shannon_entropy(ENTROPY) >= 4.0


@pytest.mark.parametrize(
    "line",
    [
        "sha = '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08'",
        "def test_contribute_diff_scan_rejects_secret_in_commit_message(): pass",
        "ARG GLAB_SHA256_ARM64=8540c4afbe63c4da023c15bfce15f2f1ef9cc1afe4a6fd6812c426b9eeab073b",
        "see openspec/changes/archive/2026-11-03-wave1-followups/specs/commons-identity/spec.md",
        "# Generated by Django 5.2.8 on 2026-11-02 10:22",
        "BASE_URL = 'https://openrouter.ai/api/v1'",
        "api_key = os.environ['OPENROUTER_API_KEY']",
        "self.private = True; os.local = 1",
        "bind = '0.0.0.0'; local = '127.0.0.1'",
        "# mail jane@example.com",
    ],
)
async def test_ordinary_code_passes(line):
    result, _ = await _scan(added("zebra-tasks/zebra_tasks/x.py", line))
    assert result["verdict"] == ROUTE_CLEAN, result["findings"]


async def test_lock_files_get_secret_rules_only_and_skip_the_llm():
    lock = added("uv.lock", 'version = "0.10.0.1"', 'url = "https://files.example/x.whl"')
    result, llm = await _scan(lock)
    assert result["verdict"] == ROUTE_CLEAN
    payload = _payload(llm)
    assert "0.10.0.1" not in payload
    result, _ = await _scan(added("uv.lock", f"token = '{GH_TOKEN}'"))
    assert "secret" in _kinds(result)


# --- fail closed -------------------------------------------------------------------------


@pytest.mark.parametrize("diff", [None, "", "   \n", 42])
async def test_empty_diff_fails_closed(diff):
    result, _ = await _scan(diff)
    assert result["verdict"] == ROUTE_REJECTED and result["failed_closed"]


async def test_diff_without_files_fails_closed():
    result, _ = await _scan("just some text\n")
    assert result["failed_closed"] and "no files" in result["reason"]


@pytest.mark.parametrize(
    "diff",
    [
        "@@ -1,1 +1,1 @@\n-a\n+b\n",  # hunk without a file
        "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1,1 +1,3 @@\n+x\n",  # ends early
        "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1,1 +1,1 @@\n?junk\n",  # bad line
    ],
)
async def test_malformed_diff_fails_closed(diff):
    with pytest.raises(DiffParseError):
        parse_diff(diff)
    result, _ = await _scan(diff)
    assert result["failed_closed"] and "does not parse" in result["reason"]


async def test_bad_pattern_fails_closed():
    result, _ = await _scan(added("a.py", "x = 1"), patterns=["("])
    assert result["failed_closed"]


async def test_size_cap_fails_closed():
    result, llm = await _scan(added("a.py", "x = 1" * 50), max_chars=100)
    assert result["failed_closed"] and "scan limit" in result["reason"]
    llm.complete.assert_not_called()


async def test_no_llm_fails_closed():
    result, _ = await _scan(added("a.py", "x = 1"), reply=None)
    assert result["failed_closed"] and "no LLM" in result["reason"]


@pytest.mark.parametrize("reply", ["", "not json", '{"findings": []}', '{"personal_data": "no"}'])
async def test_unusable_llm_reply_fails_closed(reply):
    result, _ = await _scan(added("a.py", "x = 1"), reply=reply)
    assert result["verdict"] == ROUTE_REJECTED and result["failed_closed"]


async def test_llm_error_fails_closed():
    llm = MagicMock()
    llm.complete = AsyncMock(side_effect=RuntimeError("provider down"))
    result = await scan_diff(added("a.py", "x = 1"), llm=llm)
    assert result["failed_closed"] and "provider down" in result["reason"]


async def test_llm_finds_personal_data():
    reply = json.dumps(
        {
            "personal_data": True,
            "findings": [{"path": "a.py", "kind": "health", "reason": "a named person's illness"}],
        }
    )
    result, _ = await _scan(added("a.py", "# Bob's diabetes means he skips lunch"), reply=reply)
    assert result["verdict"] == ROUTE_REJECTED and not result["failed_closed"]
    assert result["findings"] == [
        {"source": "llm", "kind": "health", "path": "a.py", "reason": "a named person's illness"}
    ]


async def test_llm_findings_without_a_true_verdict_still_reject():
    reply = json.dumps({"personal_data": False, "findings": [{"kind": "name", "reason": "x"}]})
    result, _ = await _scan(added("a.py", "x = 1"), reply=reply)
    assert result["verdict"] == ROUTE_REJECTED


async def test_llm_sees_added_lines_and_messages_not_removed_lines_or_author():
    diff = (
        "diff --git a/a.py b/a.py\nindex 1..2 100644\n--- a/a.py\n+++ b/a.py\n"
        "@@ -1,1 +1,1 @@\n-removed_marker = 1\n+added_marker = 2\n"
    )
    _, llm = await _scan(diff, commit_messages=["msg_marker"], author_name="Octo Author")
    payload = _payload(llm)
    assert "added_marker" in payload and "msg_marker" in payload
    assert "removed_marker" not in payload and "Octo Author" not in payload


# --- clean real diff ---------------------------------------------------------------------


@pytest.fixture
def real_diff() -> str:
    """A real change from this repo: ``git show --format= a497f3d`` (19 files, code, tests,
    workflow YAML, docs, an OpenSpec change), kept as a fixture so shallow CI clones work."""
    return (Path(__file__).parent / "fixtures" / "contribute_real.diff").read_text()


async def test_real_repo_diff_passes(real_diff):
    ci = (
        "diff --git a/.gitlab-ci.yml b/.gitlab-ci.yml\nindex 1..2 100644\n"
        "--- a/.gitlab-ci.yml\n+++ b/.gitlab-ci.yml\n@@ -1,1 +1,2 @@\n stages:\n+  - lint\n"
    )
    result, llm = await _scan(
        real_diff + ci,
        commit_messages=["feat: brace globs in zebra_source\n\nCloses #285\n"],
        pr_title="Brace globs in zebra_source",
        pr_body="Implements #285.",
        author_name="Octo Cat",
        github_login="octo",
        github_user_id=42,
        max_chars=200_000,
    )
    assert result["verdict"] == ROUTE_CLEAN, result["findings"]
    assert result["clean"] and not result["failed_closed"]
    assert ".gitlab-ci.yml" in result["sensitive_files"]
    assert "zebra-tasks/zebra_tasks/agent/zebra_source.py" not in result["sensitive_files"]
    assert result["added_lines"] > 10
    assert len(result["diff_sha256"]) == 64
    assert result["author_email"] == "42+octo@users.noreply.github.com"
    llm.complete.assert_called_once()


# --- the action --------------------------------------------------------------------------


def _context(extras=None):
    props: dict = {}
    ctx = MagicMock()
    ctx.process.properties = props
    ctx.process.id = "p1"
    ctx.extras = extras or {}
    ctx.set_process_property = MagicMock(side_effect=lambda k, v: props.__setitem__(k, v))
    ctx.resolve_template = MagicMock(side_effect=lambda x: x)
    return ctx


async def _run_action(properties, reply=CLEAN_REPLY, extras=None):
    provider = _llm(reply, reply)
    set_llm_factory(lambda model: provider)
    task = SimpleNamespace(id="t1", properties=properties)
    ctx = _context(extras)
    result = await ContributeDiffScanAction().run(task, ctx)
    return result, ctx


async def test_action_routes_and_stores_only_its_output():
    result, ctx = await _run_action({"diff": added("a.py", "x = 1"), "output_key": "scan"})
    assert result.success and result.next_route == ROUTE_CLEAN
    # Besides the LLM cost bookkeeping (``__total_cost__`` etc.), only its own output
    own = {k: v for k, v in ctx.process.properties.items() if not k.startswith("__")}
    assert own == {"scan": result.output}


async def test_action_rejects_and_uses_sync_service_patterns():
    sync = SimpleNamespace(confidential_patterns=["zorblax"])
    result, ctx = await _run_action(
        {"diff": added("a.py", "# zorblax")}, extras={"__commons_sync__": sync}
    )
    assert result.next_route == ROUTE_REJECTED
    assert ctx.process.properties["diff_scan"]["findings"][0]["kind"] == "confidential_pattern"


async def test_action_without_llm_fails_closed():
    def no_llm(model):
        raise ValueError("OPENROUTER_API_KEY not set")

    set_llm_factory(no_llm)
    task = SimpleNamespace(id="t1", properties={"diff": added("a.py", "x = 1")})
    ctx = _context()
    result = await ContributeDiffScanAction().run(task, ctx)
    assert result.next_route == ROUTE_REJECTED
    assert ctx.process.properties["diff_scan"]["failed_closed"]


def test_action_is_registered_and_reversible():
    from importlib.metadata import entry_points

    eps = {ep.name: ep for ep in entry_points(group="zebra.tasks")}
    assert eps["contribute_diff_scan"].load() is ContributeDiffScanAction
    assert ContributeDiffScanAction.reversibility_hint == "always_reversible"
