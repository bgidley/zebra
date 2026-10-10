"""Workflow library management."""

import logging
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from zebra.core.models import ProcessDefinition
from zebra.definitions.loader import load_definition

from zebra_agent.metrics import MetricsStore, WorkflowStats

logger = logging.getLogger(__name__)


@dataclass
class WorkflowInfo:
    """Metadata about a workflow for display and selection."""

    name: str
    description: str
    tags: list[str]
    version: int
    definition_path: Path
    use_when: str | None = None  # Detailed hint for LLM selection
    success_rate: float = 0.0
    use_count: int = 0
    retired: dict[str, Any] | None = None  # {reason, retired_at, superseded_by} (#148)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "version": self.version,
            "use_when": self.use_when,
            "success_rate": self.success_rate,
            "use_count": self.use_count,
        }


@dataclass
class WorkflowFile:
    """One active workflow file, as seen by the curator (#148)."""

    name: str
    path: Path
    tags: list[str]
    content: str
    modified_at: datetime


SYSTEM_TAG = "system"

# Tag stamped on workflows the LLM writes (creator, variant creator, optimizer).
# The dream-cycle curator may retire these for being unused; hand-written
# workflows are only retired when failing or broken (#148).
LLM_DEFINED_TAG = "llm-defined"

# Retired workflows move here: hidden from listing and selection, still loadable by name.
RETIRED_DIR = "retired"

# Retirement metadata is appended after this marker, so the original YAML text is
# kept byte-for-byte and restore() can strip it again.
_RETIRED_MARKER = "\n# --- retired by zebra (#148) ---\n"

# Tag and suffix for workflow files that would not parse; they are moved to
# ``retired/`` wrapped in a parseable stub that keeps the raw text (#158).
UNPARSEABLE_TAG = "unparseable"
_UNPARSEABLE_SUFFIX = ".unparseable.yaml"


def parse_workflow_yaml(yaml_content: str) -> dict[str, Any]:
    """Parse workflow YAML, requiring a mapping.

    Raises:
        ValueError: If the text is not valid YAML or not a mapping.
    """
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid workflow YAML: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("Invalid workflow YAML: expected a mapping")
    return data


class _BlockDumper(yaml.SafeDumper):
    """SafeDumper that writes multi-line strings (prompts) as ``|`` blocks."""


def _str_representer(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_BlockDumper.add_representer(str, _str_representer)


def tag_llm_defined(yaml_content: str) -> str:
    """Return the workflow YAML with the ``llm-defined`` tag added (#148).

    Unchanged if the tag is already present or the YAML is not a mapping.
    """
    data = yaml.safe_load(yaml_content)
    if not isinstance(data, dict):
        return yaml_content
    tags = data.get("tags") or []
    if not isinstance(tags, list):
        tags = [tags]
    if LLM_DEFINED_TAG in tags:
        return yaml_content
    data["tags"] = [*tags, LLM_DEFINED_TAG]
    return yaml.dump(data, Dumper=_BlockDumper, sort_keys=False, allow_unicode=True, width=100)


async def list_goal_workflows(library: "WorkflowLibrary") -> list[dict[str, Any]]:
    """List the workflows a goal may be routed to, as selector-ready dicts.

    This is the single source of the Agent Main Loop's ``available_workflows``:
    every entry point that creates a goal process, and the workflow selector
    itself, build the list here. Workflows tagged ``system`` are excluded.

    Args:
        library: The workflow library to list.

    Returns:
        One dict per goal workflow with ``name``, ``description``, ``tags``,
        ``success_rate`` (float 0.0-1.0), ``use_count`` and ``use_when``.
    """
    workflows = await library.list_workflows()
    return [
        {
            "name": w.name,
            "description": w.description,
            "tags": w.tags,
            "success_rate": w.success_rate,
            "use_count": w.use_count,
            "use_when": w.use_when,
        }
        for w in workflows
        if SYSTEM_TAG not in (w.tags or [])
    ]


def _recover_name(raw: str) -> str | None:
    """Best-effort workflow name from YAML text that does not parse."""
    match = re.search(r"^name:\s*[\"']?(.+?)[\"']?\s*$", raw, re.MULTILINE)
    return match.group(1) if match else None


def _free_path(directory: Path, filename: str) -> Path:
    """Return ``directory/filename``, adding ``_N`` to the stem if it is taken."""
    dest = directory / filename
    stem = Path(filename).stem
    counter = 1
    while dest.exists():
        dest = directory / f"{stem}_{counter}.yaml"
        counter += 1
    return dest


class WorkflowLibrary:
    """
    Manages a library of workflow definitions.

    Workflows are stored as YAML files in a directory structure.
    Metrics are optionally tracked via a MetricsStore.
    """

    def __init__(self, library_path: Path, metrics_store: MetricsStore | None = None):
        """
        Initialize the workflow library.

        Args:
            library_path: Directory containing workflow YAML files
            metrics_store: Optional store for workflow metrics. If None,
                          workflows will have default stats (0 uses, 0% success).
        """
        self.library_path = Path(library_path).expanduser()
        self.metrics = metrics_store
        self._cache: dict[str, ProcessDefinition] = {}

    def ensure_initialized(self) -> None:
        """Ensure the library directory exists."""
        self.library_path.mkdir(parents=True, exist_ok=True)

    async def list_workflows(self) -> list[WorkflowInfo]:
        """
        List all active workflows with their metadata and stats.

        Retired workflows (in ``retired/``) are not listed; see
        ``list_retired_workflows``.

        Returns:
            List of WorkflowInfo objects
        """
        self.ensure_initialized()
        self.quarantine_unparseable()

        workflows = []

        for yaml_file in self.library_path.glob("*.yaml"):
            try:
                info = await self._load_workflow_info(yaml_file)
                if info:
                    workflows.append(info)
            except Exception:
                # Skip invalid workflow files
                continue

        # Sort by use count (most used first), then by name
        workflows.sort(key=lambda w: (-w.use_count, w.name))

        return workflows

    async def _load_workflow_info(self, yaml_file: Path) -> WorkflowInfo | None:
        """Load workflow info from a YAML file."""
        import logging

        logger = logging.getLogger(__name__)

        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)

            if not data or "name" not in data:
                return None

            name = data["name"]
            description = data.get("description", "No description")
            tags = data.get("tags", [])
            version = data.get("version", 1)
            use_when = data.get("use_when")  # LLM selection hint

            # Get stats from metrics store (if available)
            stats = WorkflowStats(workflow_name=name)  # Default stats
            if self.metrics is not None:
                try:
                    stats = await self.metrics.get_stats(name)
                except Exception as e:
                    # Log but don't fail - use default stats if metrics unavailable
                    logger.warning(f"Failed to get stats for workflow {name}: {e}")

            return WorkflowInfo(
                name=name,
                description=description,
                tags=tags,
                version=version,
                definition_path=yaml_file,
                use_when=use_when,
                success_rate=stats.success_rate,
                use_count=stats.total_runs,
            )
        except Exception as e:
            logger.warning(f"Failed to load workflow info from {yaml_file}: {e}")
            return None

    def get_workflow(self, name: str) -> ProcessDefinition:
        """
        Load a workflow definition by name.

        Args:
            name: Workflow name

        Returns:
            ProcessDefinition object

        Raises:
            ValueError: If workflow not found
        """
        self.ensure_initialized()

        # Check cache first
        if name in self._cache:
            return self._cache[name]

        # Active workflows first, then retired ones (history and continuations
        # must still resolve a retired workflow by name).
        for yaml_file in self._files_named(name, include_retired=True):
            try:
                definition = load_definition(yaml_file)
            except Exception:
                continue
            self._cache[name] = definition
            return definition

        raise ValueError(f"Workflow not found: {name}")

    def add_workflow(
        self, yaml_content: str, filename: str | None = None, llm_defined: bool = False
    ) -> str:
        """
        Add a new workflow to the library.

        Args:
            yaml_content: YAML content of the workflow definition
            filename: Optional filename (will be generated from name if not provided)
            llm_defined: Tag the workflow ``llm-defined``, so the curator may retire
                it when unused (#148)

        Returns:
            Name of the added workflow

        Raises:
            ValueError: If the YAML does not parse or is not a mapping.
        """
        self.ensure_initialized()

        if llm_defined:
            yaml_content = tag_llm_defined(yaml_content)

        # Parse to get the name; never write a file the library cannot load (#158)
        data = parse_workflow_yaml(yaml_content)
        name = data.get("name", "untitled")

        # Generate filename if not provided
        if not filename:
            # Convert name to filename-safe string
            safe_name = name.lower().replace(" ", "_")
            safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")
            filename = f"{safe_name}.yaml"

        # Write to file
        filepath = self.library_path / filename

        # Don't overwrite existing files - add suffix if needed
        counter = 1
        while filepath.exists():
            base = filename.rsplit(".", 1)[0]
            filepath = self.library_path / f"{base}_{counter}.yaml"
            counter += 1

        with open(filepath, "w") as f:
            f.write(yaml_content)

        # Clear cache for this workflow
        if name in self._cache:
            del self._cache[name]

        return name

    def get_workflow_yaml(self, name: str) -> str:
        """
        Get the raw YAML content of a workflow.

        Args:
            name: Workflow name

        Returns:
            YAML content as string

        Raises:
            ValueError: If workflow not found
        """
        self.ensure_initialized()

        for yaml_file in self._files_named(name, include_retired=True):
            return yaml_file.read_text().split(_RETIRED_MARKER, 1)[0]

        raise ValueError(f"Workflow not found: {name}")

    @property
    def retired_path(self) -> Path:
        """Directory holding retired workflows."""
        return self.library_path / RETIRED_DIR

    @staticmethod
    def _read_named(directory: Path) -> list[tuple[str, Path]]:
        """Return ``(name, path)`` for each parseable workflow file, newest first."""
        files = []
        for yaml_file in directory.glob("*.yaml"):
            try:
                data = yaml.safe_load(yaml_file.read_text())
            except Exception:
                continue
            if isinstance(data, dict) and data.get("name"):
                files.append((data["name"], yaml_file))
        files.sort(key=lambda f: f[1].stat().st_mtime, reverse=True)
        return files

    def _files_named(self, name: str, include_retired: bool = False) -> list[Path]:
        """Return files for workflow *name*: active (newest first), then retired.

        Several active files can share a name (the optimizer saves a modified
        workflow as ``foo_1.yaml``); the newest is the current version.
        """
        self.quarantine_unparseable()
        dirs = [self.library_path, self.retired_path] if include_retired else [self.library_path]
        return [path for d in dirs for n, path in self._read_named(d) if n == name]

    def list_workflow_files(self) -> list["WorkflowFile"]:
        """Return every active workflow file, newest first.

        Unlike ``list_workflows`` this keeps every file when several share a name,
        so the curator can retire superseded copies (#148).
        """
        self.ensure_initialized()
        self.quarantine_unparseable()
        files = []
        for name, path in self._read_named(self.library_path):
            content = path.read_text()
            data = yaml.safe_load(content) or {}
            tags = data.get("tags") or []
            files.append(
                WorkflowFile(
                    name=name,
                    path=path,
                    tags=tags if isinstance(tags, list) else [tags],
                    content=content,
                    modified_at=datetime.fromtimestamp(path.stat().st_mtime, UTC),
                )
            )
        return files

    def retire(
        self,
        name: str,
        reason: str,
        superseded_by: str | None = None,
        path: Path | None = None,
    ) -> Path:
        """Retire a workflow: hide it from listing and selection, keep it loadable.

        The YAML moves to ``retired/`` with the reason appended, so run history,
        the activity view and continuations still resolve it by name.

        Args:
            name: Workflow name.
            reason: Why it was retired (shown in the UI and the dream-cycle summary).
            superseded_by: Name of the workflow that replaces it, if any.
            path: Specific file to retire (for duplicate copies that share a name);
                defaults to the newest active file with this name.

        Returns:
            The path of the retired file.

        Raises:
            ValueError: If no active workflow with this name exists.
        """
        self.ensure_initialized()
        if path is None:
            active = self._files_named(name)
            if not active:
                raise ValueError(f"Workflow not found: {name}")
            path = active[0]

        self.retired_path.mkdir(parents=True, exist_ok=True)
        dest = _free_path(self.retired_path, path.name)
        meta = {
            "reason": reason,
            "retired_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "superseded_by": superseded_by,
        }
        content = path.read_text().rstrip("\n") + "\n"
        dest.write_text(content + _RETIRED_MARKER + yaml.safe_dump({"retired": meta}))
        path.unlink()
        self._cache.pop(name, None)
        return dest

    def quarantine_unparseable(self) -> list[Path]:
        """Move active workflow files that do not parse to ``retired/`` (#158).

        Each one is replaced by a parseable stub (named ``<name> [unparseable]``,
        tagged ``unparseable``, raw text in ``unparseable_content``) with the usual
        retirement metadata, so it shows in the retired list but is never selected,
        loaded or restored, and later scans no longer re-parse it. Only the library
        directory is scanned; built-in workflows shipped in the repo are not.

        Returns:
            The retired stub files written by this call.
        """
        if not self.library_path.is_dir():
            return []
        moved = []
        for path in sorted(self.library_path.glob("*.yaml")):
            try:
                raw = path.read_text(errors="replace")
            except FileNotFoundError:
                continue  # moved or deleted by a concurrent scan
            try:
                parse_workflow_yaml(raw)
                continue
            except ValueError as e:
                error = " ".join(str(e).split())
            name = _recover_name(raw) or path.stem
            self.retired_path.mkdir(parents=True, exist_ok=True)
            dest = _free_path(self.retired_path, path.stem + _UNPARSEABLE_SUFFIX)
            # Claim the file with an atomic rename, so concurrent scans (web and
            # daemon share the library) never write two stubs for it.
            try:
                path.rename(dest)
            except FileNotFoundError:
                continue
            stub = {
                "name": f"{name} [unparseable]",
                "description": f"Unparseable workflow file {path.name}; raw text kept below.",
                "tags": [UNPARSEABLE_TAG],
                "unparseable_content": raw,
            }
            meta = {
                "reason": f"unparseable: {error}"[:500],
                "retired_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "superseded_by": None,
            }
            dest.write_text(
                yaml.dump(stub, Dumper=_BlockDumper, sort_keys=False, allow_unicode=True)
                + _RETIRED_MARKER
                + yaml.safe_dump({"retired": meta})
            )
            self._cache.pop(name, None)
            logger.warning("Retired unparseable workflow file %s → %s: %s", path, dest, error)
            moved.append(dest)
        return moved

    def restore(self, name: str) -> Path:
        """Restore a retired workflow to the active library.

        Returns:
            The path of the restored file.

        Raises:
            ValueError: If it is not retired, or an active workflow already has the name.
        """
        self.ensure_initialized()
        if self._files_named(name):
            raise ValueError(f"An active workflow named {name!r} already exists")
        retired = [p for n, p in self._read_named(self.retired_path) if n == name]
        if not retired:
            raise ValueError(f"No retired workflow named {name!r}")
        source = retired[0]
        if "unparseable_content" in (yaml.safe_load(source.read_text()) or {}):
            raise ValueError(
                f"{name!r} is an unparseable workflow file and cannot be restored; "
                "fix its YAML (kept in the retired file) and add it again"
            )
        dest = _free_path(self.library_path, source.name)
        dest.write_text(source.read_text().split(_RETIRED_MARKER, 1)[0])
        source.unlink()
        self._cache.pop(name, None)
        return dest

    async def list_retired_workflows(self) -> list[WorkflowInfo]:
        """List retired workflows, most recently retired first."""
        if not self.retired_path.exists():
            return []
        retired = []
        for yaml_file in self.retired_path.glob("*.yaml"):
            info = await self._load_workflow_info(yaml_file)
            if info is None:
                continue
            data = yaml.safe_load(yaml_file.read_text()) or {}
            info.retired = data.get("retired") or {}
            retired.append(info)
        retired.sort(key=lambda w: str(w.retired.get("retired_at", "")), reverse=True)
        return retired

    async def get_context_for_llm(self) -> str:
        """
        Format the workflow library for LLM context.

        Returns:
            Formatted string describing available workflows
        """
        workflows = await self.list_workflows()

        if not workflows:
            return "No workflows available yet."

        lines = ["Available workflows:"]
        for w in workflows:
            tags_str = ", ".join(w.tags) if w.tags else "none"
            success_pct = f"{w.success_rate:.0%}" if w.use_count > 0 else "N/A"
            lines.append(
                f"- {w.name}: {w.description} "
                f"(success: {success_pct}, uses: {w.use_count}, tags: {tags_str})"
            )

        return "\n".join(lines)

    def copy_builtin_workflows(self, builtin_path: Path) -> tuple[int, list[str]]:
        """
        Copy built-in workflows to the library, overwriting if the built-in version is newer.

        A workflow is overwritten when:
        - The destination file doesn't exist yet, OR
        - The built-in YAML has a higher ``version`` number than the installed copy.

        Args:
            builtin_path: Path to directory containing built-in workflows

        Returns:
            Tuple of (count_copied_or_updated, list_of_upgraded_workflow_names).
            Upgraded names are workflows that already existed but were replaced with a
            newer version — callers should evict any stale cached definitions for those
            names.
        """
        self.ensure_initialized()

        if not builtin_path.exists():
            return 0, []

        copied = 0
        upgraded_names: list[str] = []
        for yaml_file in builtin_path.glob("*.yaml"):
            dest = self.library_path / yaml_file.name
            if (self.retired_path / yaml_file.name).exists():
                continue  # retired by the curator or a user; don't bring it back (#148)
            if not dest.exists():
                shutil.copy(yaml_file, dest)
                try:
                    data = yaml.safe_load(yaml_file.read_text())
                    name = data.get("name") if data else None
                    if name and name in self._cache:
                        del self._cache[name]
                except Exception:
                    pass
                copied += 1
            else:
                # Overwrite if built-in has a higher version number
                try:
                    builtin_data = yaml.safe_load(yaml_file.read_text())
                    dest_data = yaml.safe_load(dest.read_text())
                    builtin_version = (builtin_data or {}).get("version", 1)
                    dest_version = (dest_data or {}).get("version", 1)
                    if builtin_version > dest_version:
                        shutil.copy(yaml_file, dest)
                        name = (builtin_data or {}).get("name")
                        if name:
                            if name in self._cache:
                                del self._cache[name]
                            upgraded_names.append(name)
                        copied += 1
                except Exception:
                    pass

        return copied, upgraded_names
