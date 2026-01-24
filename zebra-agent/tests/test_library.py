"""Tests for the library module."""

import tempfile
from pathlib import Path

import pytest

from zebra_agent.library import WorkflowInfo, WorkflowLibrary
from zebra_agent.metrics import MetricsStore, WorkflowRun


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def library_path(temp_dir):
    """Create a library directory."""
    lib_path = temp_dir / "workflows"
    lib_path.mkdir()
    return lib_path


@pytest.fixture
def library(library_path, metrics):
    """Create a WorkflowLibrary instance."""
    return WorkflowLibrary(library_path, metrics)


@pytest.fixture
def sample_workflow_yaml():
    """Sample workflow YAML content."""
    return """name: "Test Workflow"
description: "A test workflow for testing"
tags: ["test", "sample"]
use_when: "Use this when testing"
version: 1
first_task: task1

tasks:
  task1:
    name: "Test Task"
    action: llm_call
    auto: true
    properties:
      prompt: "{{goal}}"
      output_key: result

routings: []
"""


class TestWorkflowInfo:
    """Tests for WorkflowInfo dataclass."""

    def test_create_workflow_info(self, temp_dir):
        """Test creating a WorkflowInfo object."""
        info = WorkflowInfo(
            name="TestWorkflow",
            description="Test description",
            tags=["test", "sample"],
            version=1,
            definition_path=temp_dir / "test.yaml",
            use_when="Use when testing",
            success_rate=0.8,
            use_count=10,
        )
        assert info.name == "TestWorkflow"
        assert info.description == "Test description"
        assert len(info.tags) == 2
        assert info.use_when == "Use when testing"
        assert info.success_rate == 0.8
        assert info.use_count == 10

    def test_to_dict(self, temp_dir):
        """Test converting to dictionary."""
        info = WorkflowInfo(
            name="TestWorkflow",
            description="Test description",
            tags=["test"],
            version=1,
            definition_path=temp_dir / "test.yaml",
            use_when="Use when testing",
            success_rate=0.75,
            use_count=5,
        )
        data = info.to_dict()
        assert data["name"] == "TestWorkflow"
        assert data["description"] == "Test description"
        assert data["tags"] == ["test"]
        assert data["use_when"] == "Use when testing"
        assert data["success_rate"] == 0.75
        assert data["use_count"] == 5

    def test_default_values(self, temp_dir):
        """Test default values."""
        info = WorkflowInfo(
            name="TestWorkflow",
            description="Test",
            tags=[],
            version=1,
            definition_path=temp_dir / "test.yaml",
        )
        assert info.use_when is None
        assert info.success_rate == 0.0
        assert info.use_count == 0


class TestWorkflowLibraryInitialization:
    """Tests for WorkflowLibrary initialization."""

    def test_initialization(self, library):
        """Test library initialization."""
        assert library.library_path.exists() or library.library_path.parent.exists()
        assert library._cache == {}

    def test_ensure_initialized_creates_directory(self, temp_dir, metrics):
        """Test that ensure_initialized creates the directory."""
        new_path = temp_dir / "new_library"
        library = WorkflowLibrary(new_path, metrics)
        library.ensure_initialized()
        assert new_path.exists()

    def test_ensure_initialized_nested_directory(self, temp_dir, metrics):
        """Test creating nested directories."""
        nested_path = temp_dir / "a" / "b" / "c" / "workflows"
        library = WorkflowLibrary(nested_path, metrics)
        library.ensure_initialized()
        assert nested_path.exists()


class TestListWorkflows:
    """Tests for listing workflows."""

    async def test_list_workflows_empty(self, library):
        """Test listing when no workflows exist."""
        workflows = await library.list_workflows()
        assert workflows == []

    async def test_list_workflows_single(self, library, sample_workflow_yaml):
        """Test listing with a single workflow."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        workflows = await library.list_workflows()
        assert len(workflows) == 1
        assert workflows[0].name == "Test Workflow"
        assert workflows[0].description == "A test workflow for testing"
        assert "test" in workflows[0].tags

    async def test_list_workflows_multiple(self, library):
        """Test listing multiple workflows."""
        for i in range(3):
            yaml_content = f"""name: "Workflow {i}"
description: "Description {i}"
tags: ["tag{i}"]
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "test"
      output_key: result
routings: []
"""
            (library.library_path / f"workflow_{i}.yaml").write_text(yaml_content)

        workflows = await library.list_workflows()
        assert len(workflows) == 3

    async def test_list_workflows_skips_invalid(self, library, sample_workflow_yaml):
        """Test that invalid YAML files are skipped."""
        # Valid workflow
        (library.library_path / "valid.yaml").write_text(sample_workflow_yaml)
        # Invalid YAML
        (library.library_path / "invalid.yaml").write_text("{ invalid yaml: [")
        # Empty file
        (library.library_path / "empty.yaml").write_text("")

        workflows = await library.list_workflows()
        assert len(workflows) == 1

    async def test_list_workflows_with_metrics(self, library, metrics, sample_workflow_yaml):
        """Test that workflows include metrics data."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        # Record some runs
        for i in range(5):
            run = WorkflowRun.create("Test Workflow", f"Goal {i}")
            run.success = i < 4  # 4 successful
            await metrics.record_run(run)

        workflows = await library.list_workflows()
        assert len(workflows) == 1
        assert workflows[0].use_count == 5
        assert workflows[0].success_rate == 0.8

    async def test_list_workflows_sorted_by_usage(self, library, metrics):
        """Test that workflows are sorted by usage count."""
        for name, runs in [("Popular", 10), ("Medium", 5), ("Rare", 1)]:
            yaml_content = f"""name: "{name}"
description: "Test"
tags: []
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "test"
      output_key: result
routings: []
"""
            (library.library_path / f"{name.lower()}.yaml").write_text(yaml_content)
            for _ in range(runs):
                run = WorkflowRun.create(name, "Goal")
                await metrics.record_run(run)

        workflows = await library.list_workflows()
        assert workflows[0].name == "Popular"
        assert workflows[1].name == "Medium"
        assert workflows[2].name == "Rare"


class TestLoadWorkflowInfo:
    """Tests for _load_workflow_info method."""

    async def test_load_workflow_info_full(self, library, sample_workflow_yaml):
        """Test loading full workflow info."""
        yaml_file = library.library_path / "test.yaml"
        yaml_file.write_text(sample_workflow_yaml)

        info = await library._load_workflow_info(yaml_file)
        assert info is not None
        assert info.name == "Test Workflow"
        assert info.description == "A test workflow for testing"
        assert info.tags == ["test", "sample"]
        assert info.version == 1
        assert info.use_when == "Use this when testing"

    async def test_load_workflow_info_minimal(self, library):
        """Test loading workflow with minimal fields."""
        yaml_content = """name: "Minimal"
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "test"
      output_key: result
routings: []
"""
        yaml_file = library.library_path / "minimal.yaml"
        yaml_file.write_text(yaml_content)

        info = await library._load_workflow_info(yaml_file)
        assert info is not None
        assert info.name == "Minimal"
        assert info.description == "No description"
        assert info.tags == []
        assert info.version == 1
        assert info.use_when is None

    async def test_load_workflow_info_invalid(self, library):
        """Test loading invalid workflow returns None."""
        yaml_file = library.library_path / "invalid.yaml"
        yaml_file.write_text("{ invalid: yaml [")

        info = await library._load_workflow_info(yaml_file)
        assert info is None

    async def test_load_workflow_info_no_name(self, library):
        """Test loading workflow without name returns None."""
        yaml_content = """description: "No name"
first_task: task1
"""
        yaml_file = library.library_path / "noname.yaml"
        yaml_file.write_text(yaml_content)

        info = await library._load_workflow_info(yaml_file)
        assert info is None


class TestGetWorkflow:
    """Tests for getting workflow definitions."""

    def test_get_workflow_exists(self, library, sample_workflow_yaml):
        """Test getting an existing workflow."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        definition = library.get_workflow("Test Workflow")
        assert definition is not None
        assert definition.name == "Test Workflow"

    def test_get_workflow_not_found(self, library):
        """Test getting a non-existent workflow raises error."""
        with pytest.raises(ValueError, match="Workflow not found"):
            library.get_workflow("Nonexistent")

    def test_get_workflow_caches_result(self, library, sample_workflow_yaml):
        """Test that workflow definitions are cached."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        # First call
        definition1 = library.get_workflow("Test Workflow")
        # Second call should use cache
        definition2 = library.get_workflow("Test Workflow")

        assert "Test Workflow" in library._cache
        assert definition1 is definition2

    def test_get_workflow_skips_invalid_files(self, library, sample_workflow_yaml):
        """Test that invalid files are skipped when searching."""
        # Invalid file first (alphabetically)
        (library.library_path / "aaa_invalid.yaml").write_text("{ broken")
        # Valid file
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        definition = library.get_workflow("Test Workflow")
        assert definition is not None


class TestAddWorkflow:
    """Tests for adding workflows."""

    def test_add_workflow(self, library, sample_workflow_yaml):
        """Test adding a new workflow."""
        name = library.add_workflow(sample_workflow_yaml)
        assert name == "Test Workflow"

        # Verify file was created
        yaml_files = list(library.library_path.glob("*.yaml"))
        assert len(yaml_files) == 1

    def test_add_workflow_generates_filename(self, library, sample_workflow_yaml):
        """Test that filename is generated from name."""
        library.add_workflow(sample_workflow_yaml)

        # Should create test_workflow.yaml
        assert (library.library_path / "test_workflow.yaml").exists()

    def test_add_workflow_custom_filename(self, library, sample_workflow_yaml):
        """Test adding with custom filename."""
        library.add_workflow(sample_workflow_yaml, filename="custom.yaml")
        assert (library.library_path / "custom.yaml").exists()

    def test_add_workflow_no_overwrite(self, library, sample_workflow_yaml):
        """Test that existing files are not overwritten."""
        # Add first time
        library.add_workflow(sample_workflow_yaml)
        # Add again - should create new file with suffix
        library.add_workflow(sample_workflow_yaml)

        yaml_files = list(library.library_path.glob("*.yaml"))
        assert len(yaml_files) == 2

    def test_add_workflow_clears_cache(self, library, sample_workflow_yaml):
        """Test that cache is cleared when workflow is added."""
        # Add and load to populate cache
        library.add_workflow(sample_workflow_yaml)
        library.get_workflow("Test Workflow")
        assert "Test Workflow" in library._cache

        # Add again - should clear cache
        library.add_workflow(sample_workflow_yaml)
        assert "Test Workflow" not in library._cache

    def test_add_workflow_sanitizes_filename(self, library):
        """Test that special characters are removed from filename."""
        yaml_content = """name: "Workflow with Spaces & Symbols!"
description: "Test"
tags: []
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "test"
      output_key: result
routings: []
"""
        library.add_workflow(yaml_content)

        # Should create filename without special chars
        yaml_files = list(library.library_path.glob("*.yaml"))
        assert len(yaml_files) == 1
        # Filename should be sanitized
        assert "!" not in yaml_files[0].name
        assert "&" not in yaml_files[0].name


class TestGetWorkflowYaml:
    """Tests for getting raw YAML content."""

    def test_get_workflow_yaml_exists(self, library, sample_workflow_yaml):
        """Test getting YAML content of existing workflow."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        content = library.get_workflow_yaml("Test Workflow")
        assert "Test Workflow" in content
        assert "A test workflow for testing" in content

    def test_get_workflow_yaml_not_found(self, library):
        """Test getting YAML of non-existent workflow raises error."""
        with pytest.raises(ValueError, match="Workflow not found"):
            library.get_workflow_yaml("Nonexistent")

    def test_get_workflow_yaml_preserves_content(self, library, sample_workflow_yaml):
        """Test that YAML content is preserved exactly."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        content = library.get_workflow_yaml("Test Workflow")
        assert content == sample_workflow_yaml


class TestGetContextForLLM:
    """Tests for getting LLM context."""

    async def test_get_context_empty(self, library):
        """Test context when no workflows exist."""
        context = await library.get_context_for_llm()
        assert context == "No workflows available yet."

    async def test_get_context_with_workflows(self, library, sample_workflow_yaml):
        """Test context with workflows."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        context = await library.get_context_for_llm()
        assert "Available workflows:" in context
        assert "Test Workflow" in context
        assert "A test workflow for testing" in context
        assert "test, sample" in context  # tags

    async def test_get_context_with_metrics(self, library, metrics, sample_workflow_yaml):
        """Test context includes metrics."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        # Record some runs
        for i in range(10):
            run = WorkflowRun.create("Test Workflow", f"Goal {i}")
            run.success = True
            await metrics.record_run(run)

        context = await library.get_context_for_llm()
        assert "100%" in context  # success rate
        assert "uses: 10" in context


class TestCopyBuiltinWorkflows:
    """Tests for copying built-in workflows."""

    def test_copy_builtin_workflows(self, library, temp_dir, sample_workflow_yaml):
        """Test copying built-in workflows."""
        builtin_path = temp_dir / "builtin"
        builtin_path.mkdir()
        (builtin_path / "builtin.yaml").write_text(sample_workflow_yaml)

        copied = library.copy_builtin_workflows(builtin_path)
        assert copied == 1
        assert (library.library_path / "builtin.yaml").exists()

    def test_copy_builtin_workflows_no_overwrite(self, library, temp_dir, sample_workflow_yaml):
        """Test that existing workflows are not overwritten."""
        builtin_path = temp_dir / "builtin"
        builtin_path.mkdir()
        (builtin_path / "test.yaml").write_text(sample_workflow_yaml)

        # Create existing file in library
        (library.library_path / "test.yaml").write_text("existing content")

        copied = library.copy_builtin_workflows(builtin_path)
        assert copied == 0

        # Content should not be overwritten
        content = (library.library_path / "test.yaml").read_text()
        assert content == "existing content"

    def test_copy_builtin_workflows_nonexistent_path(self, library, temp_dir):
        """Test copying from non-existent path."""
        nonexistent = temp_dir / "nonexistent"

        copied = library.copy_builtin_workflows(nonexistent)
        assert copied == 0

    def test_copy_builtin_workflows_multiple(self, library, temp_dir):
        """Test copying multiple workflows."""
        builtin_path = temp_dir / "builtin"
        builtin_path.mkdir()

        for i in range(3):
            yaml_content = f"""name: "Workflow {i}"
description: "Test"
tags: []
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "test"
      output_key: result
routings: []
"""
            (builtin_path / f"workflow_{i}.yaml").write_text(yaml_content)

        copied = library.copy_builtin_workflows(builtin_path)
        assert copied == 3

        yaml_files = list(library.library_path.glob("*.yaml"))
        assert len(yaml_files) == 3

    def test_copy_builtin_workflows_partial(self, library, temp_dir, sample_workflow_yaml):
        """Test copying when some files already exist."""
        builtin_path = temp_dir / "builtin"
        builtin_path.mkdir()

        # Create 3 builtin workflows
        for i in range(3):
            yaml_content = f"""name: "Workflow {i}"
description: "Test"
tags: []
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "test"
      output_key: result
routings: []
"""
            (builtin_path / f"workflow_{i}.yaml").write_text(yaml_content)

        # Create one existing file in library
        (library.library_path / "workflow_1.yaml").write_text("existing")

        copied = library.copy_builtin_workflows(builtin_path)
        assert copied == 2  # Only 2 copied, 1 skipped


class TestListWorkflowsExceptionHandling:
    """Tests for exception handling in list_workflows."""

    async def test_list_workflows_skips_invalid_yaml(self, library):
        """Test that invalid YAML files are skipped."""
        # Create an invalid YAML file
        (library.library_path / "invalid.yaml").write_text("{{{{invalid yaml content")

        # Create a valid workflow
        valid_yaml = """name: "Valid Workflow"
description: "A valid workflow"
tags: []
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "test"
      output_key: result
routings: []
"""
        (library.library_path / "valid.yaml").write_text(valid_yaml)

        # Should only return the valid workflow
        workflows = await library.list_workflows()
        assert len(workflows) == 1
        assert workflows[0].name == "Valid Workflow"

    async def test_list_workflows_skips_non_workflow_yaml(self, library):
        """Test that non-workflow YAML files are skipped."""
        # Create a YAML file that isn't a workflow (no name field)
        (library.library_path / "config.yaml").write_text("key: value\nother: data")

        # Create a valid workflow
        valid_yaml = """name: "Valid Workflow"
description: "A valid workflow"
tags: []
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "test"
      output_key: result
routings: []
"""
        (library.library_path / "valid.yaml").write_text(valid_yaml)

        # Should only return the valid workflow
        workflows = await library.list_workflows()
        assert len(workflows) == 1

    async def test_list_workflows_skips_empty_yaml(self, library):
        """Test that empty YAML files are skipped."""
        # Create an empty YAML file
        (library.library_path / "empty.yaml").write_text("")

        # Create a valid workflow
        valid_yaml = """name: "Valid Workflow"
description: "A valid workflow"
tags: []
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "test"
      output_key: result
routings: []
"""
        (library.library_path / "valid.yaml").write_text(valid_yaml)

        # Should only return the valid workflow
        workflows = await library.list_workflows()
        assert len(workflows) == 1


class TestGetWorkflowYamlExceptionHandling:
    """Tests for exception handling in get_workflow_yaml."""

    def test_get_workflow_yaml_skips_invalid_files(self, library):
        """Test that get_workflow_yaml skips invalid YAML when searching."""
        # Create an invalid YAML file
        (library.library_path / "invalid.yaml").write_text("{{{{invalid yaml")

        # Create a valid workflow
        valid_yaml = """name: "Target Workflow"
description: "A valid workflow"
tags: []
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "test"
      output_key: result
routings: []
"""
        (library.library_path / "valid.yaml").write_text(valid_yaml)

        # Should find the valid workflow even though invalid.yaml exists
        yaml_content = library.get_workflow_yaml("Target Workflow")
        assert "Target Workflow" in yaml_content

    def test_get_workflow_yaml_not_found_with_invalid_files(self, library):
        """Test ValueError when workflow not found (with invalid files present)."""
        # Create an invalid YAML file
        (library.library_path / "invalid.yaml").write_text("{{{{invalid yaml")

        # Should raise ValueError since no valid workflow matches
        with pytest.raises(ValueError, match="Workflow not found"):
            library.get_workflow_yaml("NonExistent Workflow")
