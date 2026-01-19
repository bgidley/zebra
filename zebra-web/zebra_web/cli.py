"""CLI entry points for zebra-web."""

import subprocess
import sys


def serve():
    """Start the development server on localhost only."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "daphne",
            "-b",
            "127.0.0.1",
            "-p",
            "8000",
            "zebra_web.asgi:application",
        ],
        check=True,
    )


def serve_public():
    """Start the development server on all interfaces (for remote access)."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "daphne",
            "-b",
            "0.0.0.0",
            "-p",
            "8000",
            "zebra_web.asgi:application",
        ],
        check=True,
    )


if __name__ == "__main__":
    serve()
