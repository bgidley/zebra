"""Workflow library management."""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from zebra.core.models import ProcessDefinition
from zebra.definitions.loader import load_definition

from zebra_agent.metrics import MetricsStore


@dataclass
class WorkflowInfo:
    """Metadata about a workflow for display and selection."""

    name: str
    description: str
    tags: list[str]
    version: int
    definition_path: Path
    success_rate: float = 0.0
    use_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "version": self.version,
            "success_rate": self.success_rate,
            "use_count": self.use_count,
        }


class WorkflowLibrary:
    """
    Manages a library of workflow definitions.

    Workflows are stored as YAML files in a directory structure.
    Metrics are stored in a separate SQLite database.
    """

    def __init__(self, library_path: Path, metrics_store: MetricsStore):
        """
        Initialize the workflow library.

        Args:
            library_path: Directory containing workflow YAML files
            metrics_store: Store for workflow metrics
        """
        self.library_path = Path(library_path).expanduser()
        self.metrics = metrics_store
        self._cache: dict[str, ProcessDefinition] = {}

    def ensure_initialized(self) -> None:
        """Ensure the library directory exists."""
        self.library_path.mkdir(parents=True, exist_ok=True)

    async def list_workflows(self) -> list[WorkflowInfo]:
        """
        List all available workflows with their metadata and stats.

        Returns:
            List of WorkflowInfo objects
        """
        self.ensure_initialized()

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
        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)

            if not data or "name" not in data:
                return None

            name = data["name"]
            description = data.get("description", "No description")
            tags = data.get("tags", [])
            version = data.get("version", 1)

            # Get stats from metrics store
            stats = await self.metrics.get_stats(name)

            return WorkflowInfo(
                name=name,
                description=description,
                tags=tags,
                version=version,
                definition_path=yaml_file,
                success_rate=stats.success_rate,
                use_count=stats.total_runs,
            )
        except Exception:
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

        # Search for matching file
        for yaml_file in self.library_path.glob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)

                if data and data.get("name") == name:
                    definition = load_definition(yaml_file)
                    self._cache[name] = definition
                    return definition
            except Exception:
                continue

        raise ValueError(f"Workflow not found: {name}")

    def add_workflow(self, yaml_content: str, filename: str | None = None) -> str:
        """
        Add a new workflow to the library.

        Args:
            yaml_content: YAML content of the workflow definition
            filename: Optional filename (will be generated from name if not provided)

        Returns:
            Name of the added workflow
        """
        self.ensure_initialized()

        # Parse to get the name
        data = yaml.safe_load(yaml_content)
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

        for yaml_file in self.library_path.glob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    content = f.read()
                    data = yaml.safe_load(content)

                if data and data.get("name") == name:
                    return content
            except Exception:
                continue

        raise ValueError(f"Workflow not found: {name}")

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

    def copy_builtin_workflows(self, builtin_path: Path) -> int:
        """
        Copy built-in workflows to the library if they don't exist.

        Args:
            builtin_path: Path to directory containing built-in workflows

        Returns:
            Number of workflows copied
        """
        self.ensure_initialized()

        if not builtin_path.exists():
            return 0

        copied = 0
        for yaml_file in builtin_path.glob("*.yaml"):
            dest = self.library_path / yaml_file.name
            if not dest.exists():
                shutil.copy(yaml_file, dest)
                copied += 1

        return copied
