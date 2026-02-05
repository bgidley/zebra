"""Root conftest.py for running all tests together."""

import sys
from pathlib import Path

# Add test directories to path for importing conf modules
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "zebra-tasks" / "tests"))

# Import fixtures from zebra-tasks
# Note: zebra-agent uses standard conftest.py in its tests directory
pytest_plugins = ["zebra_tasks_conf"]
