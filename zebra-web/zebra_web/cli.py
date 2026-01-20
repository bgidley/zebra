"""CLI entry points for zebra-web."""

import subprocess
import sys


def serve():
    """Start the development server on localhost only."""
    print("Starting Zebra Web UI...")
    print("  URL: http://localhost:8000")
    print("\nPress Ctrl+C to stop.\n")

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
    )


def serve_public():
    """Start the development server on all interfaces (for remote access)."""
    import socket

    hostname = socket.gethostname()

    print("Starting Zebra Web UI (public access)...")
    print("  URL: http://0.0.0.0:8000")
    print(f"\nAccess via: http://{hostname}:8000 or your Tailscale IP")
    print("\nPress Ctrl+C to stop.\n")

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
    )


# Keep old names as aliases
dev = serve
dev_public = serve_public


if __name__ == "__main__":
    serve()
