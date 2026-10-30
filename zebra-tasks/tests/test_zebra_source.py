"""Tests for ZebraSourceAction - read-only access to Zebra's own source (#190)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from zebra.core.models import ProcessDefinition, ProcessInstance, TaskDefinition, TaskInstance
from zebra.tasks.base import ExecutionContext

from zebra_tasks.agent.zebra_source import RECOVERY_HINT, ZebraSourceAction, source_root


@pytest.fixture
def root(tmp_path: Path, monkeypatch) -> Path:
    src = tmp_path / "app"
    (src / "zebra-tasks" / "zebra_tasks").mkdir(parents=True)
    (src / "zebra-tasks" / "zebra_tasks" / "thing.py").write_text(
        "\n".join(f"line {n}" for n in range(1, 101)) + "\nclass ThingAction:\n"
    )
    (src / "zebra-agent-web").mkdir()
    (src / "zebra-agent-web" / "db.sqlite3").write_text("class ThingAction: secret db")
    (src / "zebra-agent-web" / "tmp").mkdir()
    (src / "zebra-agent-web" / "tmp" / "zebra.log").write_text("class ThingAction in a log")
    (src / ".env").write_text("ANTHROPIC_API_KEY=class ThingAction")
    (src / ".venv").mkdir()
    (src / ".venv" / "lib.py").write_text("class ThingAction: vendored")
    (src / "README.md").write_text("# Zebra\nThingAction docs\n")
    (src / "zebra-tasks" / "escape.py").symlink_to(tmp_path / "outside.py")
    (tmp_path / "outside.py").write_text("class ThingAction: outside")
    monkeypatch.setenv("ZEBRA_SOURCE_ROOT", str(src))
    return src


_DEF = ProcessDefinition(
    id="d1", name="D", first_task_id="read", tasks={"read": TaskDefinition(id="read", name="R")}
)


@pytest.fixture
def context() -> ExecutionContext:
    process = ProcessInstance(id="p1", definition_id="d1", properties={})
    return ExecutionContext(
        engine=MagicMock(),
        store=MagicMock(),
        process=process,
        process_definition=_DEF,
        task_definition=_DEF.tasks["read"],
    )


def _task(**props) -> TaskInstance:
    return TaskInstance(
        id="t1", process_id="p1", task_definition_id="read", foe_id="f1", properties=props
    )


async def test_reads_a_line_range_with_numbers(root, context):
    result = await ZebraSourceAction().run(
        _task(path="zebra-tasks/zebra_tasks/thing.py", start_line="3", end_line="4"), context
    )

    assert result.success
    assert result.output["text"] == "    3| line 3\n    4| line 4"
    assert context.process.properties["source"] == result.output["text"]


async def test_template_resolved_empty_line_bounds_read_whole_file(root, context):
    result = await ZebraSourceAction().run(
        _task(path="zebra-tasks/zebra_tasks/thing.py", start_line="", end_line=""), context
    )

    assert result.success
    assert result.output["text"].splitlines()[-1] == "  101| class ThingAction:"


async def test_read_is_capped(root, context):
    result = await ZebraSourceAction().run(
        _task(path="zebra-tasks/zebra_tasks/thing.py", max_chars=60), context
    )

    assert result.success
    assert "truncated" in result.output["text"].splitlines()[-1]
    assert len(result.output["text"].splitlines()) < 10


@pytest.mark.parametrize(
    "path",
    [
        "../outside.py",
        ".env",
        ".venv/lib.py",
        "zebra-agent-web/db.sqlite3",
        "zebra-agent-web/tmp/zebra.log",
        "zebra-tasks/escape.py",
        "/etc/passwd",
        "zebra-tasks/../../outside.py",
    ],
)
async def test_refuses_paths_outside_readable_source(root, context, path):
    result = await ZebraSourceAction().run(_task(path=path), context)

    assert not result.success
    assert "source" not in context.process.properties


async def test_absolute_path_inside_root_is_allowed(root, context):
    result = await ZebraSourceAction().run(_task(path=str(root / "README.md")), context)

    assert result.success
    assert "ThingAction docs" in result.output["text"]


async def test_search_skips_secrets_runtime_files_and_symlinks(root, context):
    result = await ZebraSourceAction().run(
        _task(operation="search", pattern=r"class \w+Action|ThingAction docs"), context
    )

    assert result.success
    assert result.output["text"].splitlines() == [
        "README.md:2: ThingAction docs",
        "zebra-tasks/zebra_tasks/thing.py:101: class ThingAction:",
    ]


async def test_search_glob_and_cap(root, context):
    result = await ZebraSourceAction().run(
        _task(operation="search", pattern="line", glob="zebra-tasks/**/*.py", max_results="3"),
        context,
    )

    lines = result.output["text"].splitlines()
    assert lines[:3] == [
        "zebra-tasks/zebra_tasks/thing.py:1: line 1",
        "zebra-tasks/zebra_tasks/thing.py:2: line 2",
        "zebra-tasks/zebra_tasks/thing.py:3: line 3",
    ]
    assert "stopped at 3" in lines[3]


@pytest.mark.parametrize(
    "props", [{"pattern": ""}, {"pattern": "("}, {"pattern": "x", "glob": "../*"}]
)
async def test_bad_search_fails(root, context, props):
    result = await ZebraSourceAction().run(_task(operation="search", **props), context)

    assert not result.success


async def test_no_matches(root, context):
    result = await ZebraSourceAction().run(_task(operation="search", pattern="zzz"), context)

    assert result.output["text"] == "No matches."


def test_default_root_is_the_checkout(monkeypatch):
    monkeypatch.delenv("ZEBRA_SOURCE_ROOT", raising=False)

    assert (source_root() / "zebra-tasks" / "zebra_tasks" / "agent" / "zebra_source.py").is_file()


# --- list and recoverable read errors (#211) ---

HIDDEN = (".env", ".venv", "sqlite3", "tmp", "escape")


def _list(**props) -> TaskInstance:
    return _task(operation="list", **props)


async def test_list_root_shows_deployed_entries(root, context):
    result = await ZebraSourceAction().run(_list(), context)

    assert result.success
    assert result.output["text"].splitlines() == [
        "README.md (25 B)",
        "zebra-agent-web/ (0 files)",
        "zebra-tasks/ (1 file)",
    ]
    assert context.process.properties["source"] == result.output["text"]


async def test_list_directory_one_level_hides_symlinks(root, context):
    result = await ZebraSourceAction().run(_list(path="zebra-tasks"), context)

    assert result.output["text"] == "zebra-tasks/zebra_tasks/ (1 file)"


async def test_list_by_glob_is_recursive_and_root_relative(root, context):
    result = await ZebraSourceAction().run(_list(path="zebra-tasks", glob="**/*.py"), context)

    assert result.output["text"] == "zebra-tasks/zebra_tasks/thing.py"


async def test_list_never_names_hidden_entries(root, context):
    for props in ({}, {"path": "zebra-agent-web"}, {"glob": "**/*"}):
        result = await ZebraSourceAction().run(_list(**props), context)

        assert result.success
        assert not any(h in result.output["text"] for h in HIDDEN), props


async def test_list_is_capped(root, context):
    for n in range(5):
        (root / "zebra-tasks" / "zebra_tasks" / f"m{n}.py").write_text("x")

    result = await ZebraSourceAction().run(_list(glob="**/*.py", max_results="2"), context)

    lines = result.output["text"].splitlines()
    assert len(lines) == 3
    assert lines[2] == "... 4 more; narrow it with path or glob"


async def test_list_empty_directory_and_no_glob_match(root, context):
    (root / "zebra-tasks" / "empty").mkdir()

    empty = await ZebraSourceAction().run(_list(path="zebra-tasks/empty"), context)
    no_match = await ZebraSourceAction().run(_list(glob="**/*.rs"), context)

    assert empty.output["text"] == "zebra-tasks/empty has no readable source."
    assert no_match.output["text"] == "No files match '**/*.rs' under the source root."


@pytest.mark.parametrize(
    "props",
    [
        {"path": "../"},
        {"path": ".venv"},
        {"path": "/etc"},
        {"path": "zebra-agent-web/tmp"},
        {"glob": "../*"},
    ],
)
async def test_list_refuses_hidden_and_outside(root, context, props):
    result = await ZebraSourceAction().run(_list(**props), context)

    assert not result.success
    assert "source" not in context.process.properties


async def test_list_of_a_file_returns_its_entry(root, context):
    result = await ZebraSourceAction().run(_list(path="zebra-tasks/zebra_tasks/thing.py"), context)

    assert result.success
    assert result.output["text"] == "zebra-tasks/zebra_tasks/thing.py (811 B)"
    assert context.process.properties["source"] == result.output["text"]


async def test_list_of_a_hidden_file_is_still_refused(root, context):
    result = await ZebraSourceAction().run(_list(path="zebra-agent-web/db.sqlite3"), context)

    assert not result.success
    assert "never reads" in result.error


async def test_ambiguous_typo_suggests_the_right_one(root, context):
    (root / "zebra-tasks" / "zebra_tasks" / "thin.py").write_text("x")

    result = await ZebraSourceAction().run(_task(path="zebra-tasks/zebra_tasks/thng.py"), context)

    assert not result.success
    assert "zebra-tasks/zebra_tasks/thing.py" in result.error.split("Did you mean: ")[1]
    assert "list_zebra_source" in result.error and "search_zebra_source" in result.error


async def test_file_name_in_several_places_is_suggested_by_full_path(root, context):
    (root / "zebra-agent-web" / "thing.py").write_text("x")

    result = await ZebraSourceAction().run(_task(path="zebra-tasks/thing.py"), context)

    assert not result.success
    assert "zebra-tasks/zebra_tasks/thing.py" in result.error
    assert "zebra-agent-web/thing.py" in result.error


async def test_no_close_match_gives_only_the_hint(root, context):
    result = await ZebraSourceAction().run(_task(path="zebra-tasks/qqqq/zzzzzz.yaml"), context)

    assert "Did you mean" not in result.error
    assert "does not exist" in result.error and "list_zebra_source" in result.error


async def test_at_most_five_suggestions(root, context):
    for n in range(8):
        (root / "zebra-tasks" / f"pkg{n}").mkdir()
        (root / "zebra-tasks" / f"pkg{n}" / "same.py").write_text("x")

    result = await ZebraSourceAction().run(_task(path="zebra-tasks/same.py"), context)

    suggested = result.error.split("Did you mean: ")[1].split("?")[0].split(", ")
    assert len(suggested) == 5
    assert all(s.endswith("/same.py") for s in suggested)


async def test_suggestions_never_name_hidden_entries(root, context):
    for path in ("zebra-tasks/escap.py", "zebra-agent-web/db.sqlite", "zebra-agent-web/tmp.log"):
        result = await ZebraSourceAction().run(_task(path=path), context)

        assert not result.success
        assert not any(h in result.error.replace(path, "") for h in HIDDEN), path


async def test_directory_read_returns_its_listing(root, context):
    result = await ZebraSourceAction().run(_task(path="zebra-tasks"), context)

    assert not result.success
    assert "is a directory" in result.error
    assert "zebra-tasks/zebra_tasks/ (1 file)" in result.error


@pytest.mark.parametrize(
    "props",
    [
        {"path": ""},
        {"path": "../outside.py"},
        {"path": ".env"},
        {"path": "zebra-tasks"},
        {"path": "zebra-tasks/qqqq/zzzzzz.yaml"},
        {"path": "zebra_qqqq/zzzzzz.yaml"},
        {"path": "specs/zebra-as-is.md"},
        {"operation": "list", "path": "zebra-tasks/nope"},
        {"operation": "search", "pattern": "("},
        {"operation": "search", "pattern": "x", "glob": "../*"},
    ],
)
async def test_every_failure_ends_with_the_recovery_hint(root, context, props):
    result = await ZebraSourceAction().run(_task(**props), context)

    assert not result.success
    assert result.error.endswith(RECOVERY_HINT)
    assert result.error.count(RECOVERY_HINT) == 1
    assert "?." not in result.error and ".." not in result.error.replace("../", "")


async def test_too_large_file_fails_with_the_hint(root, context, monkeypatch):
    monkeypatch.setattr("zebra_tasks.agent.zebra_source.MAX_FILE_BYTES", 10)

    result = await ZebraSourceAction().run(_task(path="zebra-tasks/zebra_tasks/thing.py"), context)

    assert "too large to read. " + RECOVERY_HINT == result.error.split("' is ", 1)[1]


async def test_undeployed_entry_names_what_is_deployed(root, context):
    result = await ZebraSourceAction().run(_task(path="specs/zebra-as-is.md"), context)

    assert not result.success
    assert "'specs/zebra-as-is.md' is not deployed" in result.error
    assert "Deployed: README.md, zebra-agent-web/, zebra-tasks/." in result.error


# --- path guard and auto-recovery (#221, #223) ---


@pytest.mark.parametrize(
    "path",
    [
        "zebra-tasks/zebra_tasks/thng.py",  # typo
        "zebra-tasks/thing.py",  # right name, wrong directory
        "zebra_tasks/thing.py",  # missing package prefix: not an allowlisted entry
    ],
)
async def test_one_clear_match_is_read_with_a_note(root, context, path):
    result = await ZebraSourceAction().run(_task(path=path, start_line="2", end_line="3"), context)

    assert result.success
    assert result.output["path"] == "zebra-tasks/zebra_tasks/thing.py"
    assert result.output["text"].splitlines() == [
        f"Note: '{path}' does not exist; read 'zebra-tasks/zebra_tasks/thing.py' instead "
        "(the only close match).",
        "    2| line 2",
        "    3| line 3",
    ]
    assert context.process.properties["source"] == result.output["text"]


async def test_exact_read_reports_its_path_and_no_note(root, context):
    result = await ZebraSourceAction().run(_task(path="README.md"), context)

    assert result.output["path"] == "README.md"
    assert not result.output["text"].startswith("Note:")


async def test_weak_match_is_not_guessed(root, context):
    result = await ZebraSourceAction().run(_task(path="zebra-tasks/zebra_tasks/thx.py"), context)

    assert not result.success
    assert "Did you mean: zebra-tasks/zebra_tasks/thing.py?" in result.error


async def test_two_close_paths_are_ambiguous(root, context):
    (root / "zebra-tasks" / "zebra_tasks" / "thin.py").write_text("x")

    result = await ZebraSourceAction().run(_task(path="zebra-tasks/zebra_tasks/thng.py"), context)

    assert not result.success
    assert "source" not in context.process.properties


async def test_auto_recovery_never_reads_hidden_files(root, context):
    (root / "zebra-tasks" / "notes.sqlite3").write_text("SECRET")
    (root / "zebra-tasks" / "tmp").mkdir()
    (root / "zebra-tasks" / "tmp" / "run.log").write_text("SECRET")
    (root / "zebra-tasks" / ".hidden.py").write_text("SECRET")

    for path in (
        "zebra-tasks/x/notes.sqlite3",
        "zebra-tasks/run.log",
        "zebra-tasks/hidden.py",
        "zebra-tasks/escape.py.bak",
        "zebra-tasks/zebra_tasks/escape.py",
        "zebra-tasks/zebra_tasks/lib.py",
    ):
        result = await ZebraSourceAction().run(_task(path=path), context)

        assert not result.success, path
        assert "SECRET" not in result.error and "outside" not in result.error, path
        assert "source" not in context.process.properties, path


@pytest.mark.parametrize("path", ["../etc/passwd", "/etc/passwd", "zebra-tasks/escape.py"])
async def test_outside_paths_say_so(root, context, path):
    result = await ZebraSourceAction().run(_task(path=path), context)

    assert result.error.startswith(f"'{path}' is outside the Zebra source tree. ")


@pytest.mark.parametrize(
    "path", [".env", ".venv/lib.py", "zebra-agent-web/db.sqlite3", "zebra-agent-web/tmp/zebra.log"]
)
async def test_hidden_paths_say_why(root, context, path):
    result = await ZebraSourceAction().run(_task(path=path), context)

    assert result.error.startswith(
        f"'{path}' is a hidden, secret or runtime file Zebra never reads. "
    )


async def test_existing_entry_off_the_allowlist_is_refused(root, context):
    (root / "legacy").mkdir()
    (root / "legacy" / "Engine.java").write_text("class Engine {}")

    for path in ("legacy/Engine.java", "legacy/Engin.java"):
        result = await ZebraSourceAction().run(_task(path=path), context)

        assert result.error.startswith(f"'{path}' is not part of Zebra's readable source. ")


async def test_unknown_entry_without_a_match_names_the_tree(root, context):
    result = await ZebraSourceAction().run(_task(path="zebra_qqqq/zzzzzz.yaml"), context)

    assert not result.success
    assert (
        "the source tree has no 'zebra_qqqq'. It has README.md, zebra-agent-web/, zebra-tasks/."
        in result.error
    )
