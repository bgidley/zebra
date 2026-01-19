"""CLI entry points for zebra-web."""

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path


def _get_frontend_dir() -> Path:
    """Get the frontend directory path."""
    return Path(__file__).parent.parent / "frontend"


def _get_npm() -> str:
    """Find npm executable, setting up fnm if needed."""
    # Check if npm is already in PATH
    npm = shutil.which("npm")
    if npm:
        return npm

    # Try to set up fnm
    fnm_dir = Path.home() / ".local/share/fnm"
    if fnm_dir.exists():
        # Source fnm environment
        fnm = shutil.which("fnm") or str(fnm_dir / "fnm")
        if Path(fnm).exists():
            try:
                # Get fnm env and update our environment
                result = subprocess.run(
                    [fnm, "env", "--shell", "bash"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                for line in result.stdout.splitlines():
                    if line.startswith("export "):
                        # Parse: export VAR="value" or export PATH="...":"$PATH"
                        parts = line[7:].split("=", 1)
                        if len(parts) == 2:
                            key = parts[0]
                            value = parts[1].strip('"').strip("'")
                            # Handle PATH specially - expand $PATH
                            if key == "PATH":
                                value = value.replace('":', ":").replace(':"$PATH"', "")
                                value = value + ":" + os.environ.get("PATH", "")
                            os.environ[key] = value

                # Now try to find npm again
                npm = shutil.which("npm")
                if npm:
                    return npm
            except subprocess.CalledProcessError:
                pass

    raise RuntimeError(
        "npm not found. Please install Node.js:\n"
        "  curl -fsSL https://fnm.vercel.app/install | bash\n"
        "  source ~/.bashrc\n"
        "  fnm install 22"
    )


def _start_backend(host: str = "127.0.0.1") -> subprocess.Popen:
    """Start the Django backend server."""
    return subprocess.Popen(
        [sys.executable, "-m", "daphne", "-b", host, "-p", "8000", "zebra_web.asgi:application"],
    )


def _start_frontend(host: str = "localhost") -> subprocess.Popen:
    """Start the Vite frontend dev server."""
    frontend_dir = _get_frontend_dir()
    npm = _get_npm()

    # Check if node_modules exists
    if not (frontend_dir / "node_modules").exists():
        print("Installing frontend dependencies...")
        subprocess.run([npm, "install"], cwd=frontend_dir, check=True)

    cmd = [npm, "run", "dev"]
    if host != "localhost":
        cmd.extend(["--", "--host", host])

    return subprocess.Popen(cmd, cwd=frontend_dir)


def serve():
    """Start the backend server on localhost only."""
    proc = _start_backend("127.0.0.1")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


def serve_public():
    """Start the backend server on all interfaces (for remote access)."""
    proc = _start_backend("0.0.0.0")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


def dev():
    """Start both backend and frontend servers for local development."""
    print("Starting Zebra Web UI...")
    print("  Backend:  http://localhost:8000")
    print("  Frontend: http://localhost:3000")
    print("\nPress Ctrl+C to stop both servers.\n")

    backend = _start_backend("127.0.0.1")
    frontend = _start_frontend("localhost")

    def cleanup(signum=None, frame=None):
        print("\nShutting down...")
        frontend.terminate()
        backend.terminate()
        frontend.wait()
        backend.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Wait for either to exit
    try:
        while True:
            if backend.poll() is not None:
                print("Backend exited unexpectedly")
                frontend.terminate()
                sys.exit(1)
            if frontend.poll() is not None:
                print("Frontend exited unexpectedly")
                backend.terminate()
                sys.exit(1)
            signal.pause()
    except KeyboardInterrupt:
        cleanup()


def dev_public():
    """Start both servers on all interfaces (for Tailscale/remote access)."""
    import socket

    hostname = socket.gethostname()

    print("Starting Zebra Web UI (public access)...")
    print("  Backend:  http://0.0.0.0:8000")
    print("  Frontend: http://0.0.0.0:3000")
    print(f"\nAccess via: http://{hostname}:3000 or your Tailscale IP")
    print("\nPress Ctrl+C to stop both servers.\n")

    backend = _start_backend("0.0.0.0")
    frontend = _start_frontend("0.0.0.0")

    def cleanup(signum=None, frame=None):
        print("\nShutting down...")
        frontend.terminate()
        backend.terminate()
        frontend.wait()
        backend.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    try:
        while True:
            if backend.poll() is not None:
                print("Backend exited unexpectedly")
                frontend.terminate()
                sys.exit(1)
            if frontend.poll() is not None:
                print("Frontend exited unexpectedly")
                backend.terminate()
                sys.exit(1)
            signal.pause()
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    dev()
