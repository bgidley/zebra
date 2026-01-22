"""CLI entry points for zebra-agent-web.

Provides commands to run the development and production servers:
- zebra-web-agent: Production server on localhost:8000
- zebra-web-agent-public: Production server on 0.0.0.0:8000
- zebra-web-agent-dev: Development server on localhost:8000
- zebra-web-agent-dev-public: Development server on 0.0.0.0:8000
"""

import os
import sys


def _setup_django():
    """Set up Django settings module."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zebra_agent_web.settings")


def serve():
    """Run the production ASGI server with Daphne on localhost:8000."""
    _setup_django()
    from daphne.cli import CommandLineInterface

    sys.argv = ["daphne", "-b", "127.0.0.1", "-p", "8000", "zebra_agent_web.asgi:application"]
    CommandLineInterface().run(sys.argv[1:])


def serve_public():
    """Run the production ASGI server with Daphne on 0.0.0.0:8000."""
    _setup_django()
    from daphne.cli import CommandLineInterface

    sys.argv = ["daphne", "-b", "0.0.0.0", "-p", "8000", "zebra_agent_web.asgi:application"]
    CommandLineInterface().run(sys.argv[1:])


def dev():
    """Run the Django development server on localhost:8000."""
    _setup_django()
    from django.core.management import execute_from_command_line

    sys.argv = ["manage.py", "runserver", "127.0.0.1:8000"]
    execute_from_command_line(sys.argv)


def dev_public():
    """Run the Django development server on 0.0.0.0:8000."""
    _setup_django()
    from django.core.management import execute_from_command_line

    sys.argv = ["manage.py", "runserver", "0.0.0.0:8000"]
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    dev()
