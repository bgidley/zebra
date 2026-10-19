"""ZebraSourceAction - read-only access to Zebra's own source code (#190, #211).

Lets Zebra list, read and search the code it is running, e.g. to review a change
against its intended outcomes. The root is ``ZEBRA_SOURCE_ROOT`` or, by default,
the checkout the installed ``zebra_tasks`` package lives in (``/app`` in the
prod image, the repo root in development). Only allowlisted top-level entries
are visible; dot-entries (``.env``, ``.venv``, ``.git``), databases and runtime
directories are refused. A bad path fails with the nearest existing paths and a
hint to list or search, so an agent can recover. Nothing is ever written.
"""

import difflib
import fnmatch
import logging
import os
import re
from pathlib import Path

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)

ALLOWED_TOP_LEVEL = {
    "zebra-py",
    "zebra-tasks",
    "zebra-agent",
    "zebra-agent-web",
    "specs",
    "openspec",
    "docs",
    "scripts",
    "deploy",
    "pyproject.toml",
    "version.json",
}
DENIED_PARTS = {"__pycache__", "tmp", "staticfiles", "node_modules", "fixtures"}
DENIED_SUFFIXES = {".sqlite3", ".db", ".pem", ".key", ".pyc"}
MAX_FILE_BYTES = 1_000_000
MAX_SUGGESTIONS = 5
RECOVERY_HINT = "Use list_zebra_source to see what exists, or search_zebra_source to find a name."


class SourceAccessError(Exception):
    """Raised when a path is outside what Zebra may read."""


def source_root() -> Path:
    """Return the root of Zebra's source tree."""
    configured = os.environ.get("ZEBRA_SOURCE_ROOT")
    if configured:
        return Path(configured).resolve()
    # zebra_tasks/agent/zebra_source.py -> zebra_tasks -> zebra-tasks -> checkout root
    return Path(__file__).resolve().parents[3]


def _allowed(rel: Path) -> bool:
    """Whether a root-relative path is visible to Zebra."""
    parts = rel.parts
    if not parts:
        return False
    top = parts[0]
    if top not in ALLOWED_TOP_LEVEL and not (len(parts) == 1 and top.endswith(".md")):
        return False
    if any(p.startswith(".") or p in DENIED_PARTS for p in parts):
        return False
    return rel.suffix not in DENIED_SUFFIXES


def resolve_source_path(root: Path, path: str) -> Path:
    """Resolve ``path`` inside ``root`` or raise SourceAccessError."""
    path = (path or "").strip()
    if not path:
        raise SourceAccessError("No path given")
    candidate = Path(path)
    candidate = (candidate if candidate.is_absolute() else root / candidate).resolve()
    try:
        rel = candidate.relative_to(root)
    except ValueError:
        raise SourceAccessError(f"'{path}' is outside the Zebra source tree") from None
    if not _allowed(rel):
        raise SourceAccessError(f"'{path}' is not readable source. {RECOVERY_HINT}")
    return candidate


def _source_files(root: Path, under: Path | None = None):
    """Yield readable files under the allowed top-level entries (or ``under``), in order."""
    for top in [under] if under is not None else sorted(root.iterdir()):
        if top.is_symlink() or not _allowed(top.relative_to(root)):
            continue
        if top.is_file():
            yield top
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            here = Path(dirpath)
            dirnames[:] = sorted(
                d
                for d in dirnames
                if not (here / d).is_symlink() and _allowed((here / d).relative_to(root))
            )
            for name in sorted(filenames):
                path = here / name
                if not path.is_symlink() and _allowed(path.relative_to(root)):
                    yield path


def _size(n: int) -> str:
    """Human-readable file size."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _deployed_entries(root: Path) -> list[str]:
    """The allowed top-level entries present under ``root``, directories with ``/``."""
    return [
        e.name + ("/" if e.is_dir() else "")
        for e in sorted(root.iterdir())
        if not e.is_symlink() and _allowed(e.relative_to(root))
    ]


def list_directory(root: Path, directory: Path) -> list[str]:
    """One level of ``directory``: subdirectories with file counts, files with sizes."""
    lines = []
    for entry in sorted(directory.iterdir()):
        rel = entry.relative_to(root)
        if entry.is_symlink() or not _allowed(rel):
            continue
        if entry.is_dir():
            count = sum(1 for _ in _source_files(root, entry))
            lines.append(f"{rel.as_posix()}/ ({count} file{'' if count == 1 else 's'})")
        elif entry.is_file():
            lines.append(f"{rel.as_posix()} ({_size(entry.stat().st_size)})")
    return lines


def suggest_paths(root: Path, rel: Path) -> list[str]:
    """Up to MAX_SUGGESTIONS readable files near ``rel``: same file name first, then close."""
    files = [f.relative_to(root).as_posix() for f in _source_files(root)]
    wanted = rel.as_posix()
    same_name = [f for f in files if f.rsplit("/", 1)[-1] == rel.name]
    same_name.sort(key=lambda f: -difflib.SequenceMatcher(None, wanted, f).ratio())
    close = difflib.get_close_matches(wanted, files, n=MAX_SUGGESTIONS, cutoff=0.6)
    return list(dict.fromkeys(same_name + close))[:MAX_SUGGESTIONS]


def missing_path_message(root: Path, path: str, resolved: Path) -> str:
    """Why ``path`` cannot be read, with what to try instead."""
    rel = resolved.relative_to(root)
    if not (root / rel.parts[0]).exists():
        deployed = ", ".join(_deployed_entries(root))
        return (
            f"'{path}' is not deployed: '{rel.parts[0]}' is not in the source tree. "
            f"Deployed: {deployed}. {RECOVERY_HINT}"
        )
    message = f"'{path}' does not exist."
    suggestions = suggest_paths(root, rel)
    if suggestions:
        message += " Did you mean: " + ", ".join(suggestions) + "?"
    return f"{message} {RECOVERY_HINT}"


def _glob_match(rel: Path, glob: str) -> bool:
    """Match a root-relative path against a glob; ``**/`` also matches top-level files."""
    text = rel.as_posix()
    if fnmatch.fnmatch(text, glob):
        return True
    return glob.startswith("**/") and fnmatch.fnmatch(text, glob[3:])


def _checked_glob(glob: str) -> str:
    """Return ``glob`` if it stays inside the source tree, else raise SourceAccessError."""
    if ".." in Path(glob).parts or Path(glob).is_absolute():
        raise SourceAccessError("glob must be relative to the source tree")
    return glob


def _as_int(value: object, default: int) -> int:
    """Parse an int property that may arrive as a template-resolved string."""
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


class ZebraSourceAction(TaskAction):
    """List, read or regex-search Zebra's own source tree.

    Example workflow usage:
        ```yaml
        read:
          action: zebra_source
          properties:
            operation: read
            path: "{{path}}"
            start_line: "{{start_line}}"
            output_key: source
        ```
    """

    description = (
        "List, read or regex-search Zebra's own deployed source code (read-only, "
        "sandboxed to the source tree)."
    )
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="operation",
            type="string",
            description="'read', 'search' or 'list'",
            required=False,
            default="read",
        ),
        ParameterDef(
            name="path",
            type="string",
            description="File to read, or directory to list (default: the root)",
            required=False,
        ),
        ParameterDef(
            name="start_line", type="int", description="First line to read", required=False
        ),
        ParameterDef(name="end_line", type="int", description="Last line to read", required=False),
        ParameterDef(
            name="pattern", type="string", description="Regex to search for", required=False
        ),
        ParameterDef(
            name="glob",
            type="string",
            description="Files to search or list, e.g. '**/*.py' (default: all source)",
            required=False,
        ),
        ParameterDef(
            name="max_chars", type="int", description="Read cap", required=False, default=12000
        ),
        ParameterDef(
            name="max_results",
            type="int",
            description="Search cap (default 50) or list cap (default 200)",
            required=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property for the result text",
            required=False,
            default="source",
        ),
    ]
    outputs = [
        ParameterDef(
            name="text", type="string", description="File lines, search hits or a listing"
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """List, read or search, storing the text under ``output_key``."""
        props = {
            k: context.resolve_template(v) if isinstance(v, str) else v
            for k, v in task.properties.items()
        }
        root = source_root()
        try:
            operation = props.get("operation", "read")
            if operation == "search":
                text = self._search(root, props)
            elif operation == "list":
                text = self._list(root, props)
            else:
                text = self._read(root, props)
        except SourceAccessError as e:
            return TaskResult.fail(str(e))

        context.set_process_property(props.get("output_key") or "source", text)
        return TaskResult.ok(output={"text": text})

    def _read(self, root: Path, props: dict) -> str:
        raw = props.get("path", "")
        path = resolve_source_path(root, raw)
        if path.is_dir():
            listing = "\n".join(list_directory(root, path)) or "(no readable source)"
            raise SourceAccessError(
                f"'{raw}' is a directory, not a file. It contains:\n{listing}\n"
                "Read one of these paths."
            )
        if not path.is_file():
            raise SourceAccessError(missing_path_message(root, raw, path))
        if path.stat().st_size > MAX_FILE_BYTES:
            raise SourceAccessError(f"'{props.get('path')}' is too large to read")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(_as_int(props.get("start_line"), 1), 1)
        end = min(_as_int(props.get("end_line"), len(lines)), len(lines))
        max_chars = _as_int(props.get("max_chars"), 12000)

        out: list[str] = []
        size = 0
        for n in range(start, end + 1):
            line = f"{n:5}| {lines[n - 1]}"
            if size + len(line) > max_chars:
                out.append(
                    f"... truncated at line {n - 1} of {len(lines)}; read on with start_line"
                )
                break
            out.append(line)
            size += len(line) + 1
        return "\n".join(out)

    def _search(self, root: Path, props: dict) -> str:
        pattern = props.get("pattern") or ""
        if not pattern:
            raise SourceAccessError("No search pattern given")
        try:
            regex = re.compile(pattern)
        except re.error as e:
            raise SourceAccessError(f"Invalid regex: {e}") from None
        glob = _checked_glob(props.get("glob") or "**/*")
        max_results = _as_int(props.get("max_results"), 50)

        hits: list[str] = []
        for path in _source_files(root):
            rel = path.relative_to(root)
            if not _glob_match(rel, glob) or path.stat().st_size > MAX_FILE_BYTES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    hits.append(f"{rel}:{n}: {line.strip()[:200]}")
                    if len(hits) >= max_results:
                        hits.append(f"... stopped at {max_results} matches; narrow the search")
                        return "\n".join(hits)
        return "\n".join(hits) if hits else "No matches."

    def _list(self, root: Path, props: dict) -> str:
        raw = (props.get("path") or "").strip()
        directory = root if raw in ("", ".", "./") else resolve_source_path(root, raw)
        label = raw or "the source root"
        if directory.is_file():
            raise SourceAccessError(f"'{raw}' is a file; read it with read_zebra_source")
        if not directory.is_dir():
            raise SourceAccessError(missing_path_message(root, raw, directory))
        max_results = _as_int(props.get("max_results"), 200)

        glob = props.get("glob")
        if glob:
            glob = _checked_glob(glob)
            under = None if directory == root else directory
            lines = [
                f.relative_to(root).as_posix()
                for f in _source_files(root, under)
                if _glob_match(f.relative_to(root), glob)
            ]
            if not lines:
                return f"No files match '{glob}' under {label}."
        else:
            lines = list_directory(root, directory)
            if not lines:
                return f"{label} has no readable source."
        if len(lines) > max_results:
            more = len(lines) - max_results
            lines = lines[:max_results] + [f"... {more} more; narrow it with path or glob"]
        return "\n".join(lines)
