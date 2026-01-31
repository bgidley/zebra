#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys
from pathlib import Path


def _load_env():
    """Load environment variables from .env file."""
    try:
        from dotenv import load_dotenv

        # Try to find .env in current directory or parent directories
        current = Path.cwd()
        for path in [current, current.parent, current.parent.parent]:
            env_file = path / ".env"
            if env_file.exists():
                load_dotenv(env_file)
                print(f"Loaded environment from {env_file}")
                break
    except ImportError:
        # python-dotenv not installed, skip
        pass


def main():
    """Run administrative tasks."""
    # Load .env file before Django setup
    _load_env()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zebra_agent_web.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
