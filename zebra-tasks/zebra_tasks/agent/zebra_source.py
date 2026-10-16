"""ZebraSourceAction - read-only access to Zebra's own source code (#190).

Lets Zebra read and search the code it is running, e.g. to review a change
against its intended outcomes. The root is ``ZEBRA_SOURCE_ROOT`` or, by default,
the checkout the installed ``zebra_tasks`` package lives in (``/app`` in the
prod image, the repo root in development). Only allowlisted top-level entries
are visible; dot-entries (``.env``, ``.venv``, ``.git``), databases and runtime
directories are refused. Nothing is ever written.
"""

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
        raise SourceAccessError(f"'{path}' is not readable source")
    return candidate


def _source_files(root: Path):
    """Yield readable files under the allowed top-level entries, in a stable order."""
    for top in sorted(root.iterdir()):
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


def _glob_match(rel: Path, glob: str) -> bool:
    """Match a root-relative path against a glob; ``**/`` also matches top-level files."""
    text = rel.as_posix()
    if fnmatch.fnmatch(text, glob):
        return True
    return glob.startswith("**/") and fnmatch.fnmatch(text, glob[3:])


def _as_int(value: object, default: int) -> int:
    """Parse an int property that may arrive as a template-resolved string."""
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


class ZebraSourceAction(TaskAction):
    """Read a file from, or regex-search, Zebra's own source tree.

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
        "Read a file from, or regex-search, Zebra's own deployed source code (read-only, "
        "sandboxed to the source tree)."
    )
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="operation",
            type="string",
            description="'read' or 'search'",
            required=False,
            default="read",
        ),
        ParameterDef(name="path", type="string", description="File to read", required=False),
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
            description="Files to search, e.g. '**/*.py' (default: all source)",
            required=False,
        ),
        ParameterDef(
            name="max_chars", type="int", description="Read cap", required=False, default=12000
        ),
        ParameterDef(
            name="max_results", type="int", description="Search cap", required=False, default=50
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
        ParameterDef(name="text", type="string", description="File lines or search hits"),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Read or search, storing the text under ``output_key``."""
        props = {
            k: context.resolve_template(v) if isinstance(v, str) else v
            for k, v in task.properties.items()
        }
        root = source_root()
        try:
            if props.get("operation", "read") == "search":
                text = self._search(root, props)
            else:
                text = self._read(root, props)
        except SourceAccessError as e:
            return TaskResult.fail(str(e))

        context.set_process_property(props.get("output_key") or "source", text)
        return TaskResult.ok(output={"text": text})

    def _read(self, root: Path, props: dict) -> str:
        path = resolve_source_path(root, props.get("path", ""))
        if not path.is_file():
            raise SourceAccessError(f"'{props.get('path')}' is not a file")
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
        glob = props.get("glob") or "**/*"
        if ".." in Path(glob).parts or Path(glob).is_absolute():
            raise SourceAccessError("glob must be relative to the source tree")
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
