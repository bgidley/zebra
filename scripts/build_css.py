#!/usr/bin/env python3
"""Compile the web UI stylesheet with a pinned Tailwind v4 standalone binary.

Downloads the Tailwind CLI for this platform on first use, checks it against
the pinned sha256, caches it under ``~/.cache/zebra/tailwindcss/<version>/``
and compiles ``zebra-agent-web/static/css/src/app.css`` into
``zebra-agent-web/static/css/app.css``. No Node.js needed. Stdlib only, so it
runs in the Docker builder, the CI shell runner and on a laptop alike.

Usage:
    build_css.py            # one-off minified build
    build_css.py --watch    # rebuild on template changes during development

Bumping Tailwind: change TAILWIND_VERSION and replace the hashes with the
matching lines from that release's ``sha256sums.txt``.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import stat
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

TAILWIND_VERSION = "v4.3.3"

# From https://github.com/tailwindlabs/tailwindcss/releases/download/v4.3.3/sha256sums.txt
SHA256 = {
    "tailwindcss-linux-arm64": "55fd0b241214eff3de1e8ee4f22796662f2d2e7a49bcfca7477cfd0bac398195",
    "tailwindcss-linux-x64": "dc61b3ac6b8c9ca874c0cc4c57b2409791a64c5540404ca5f5367360babc313a",
    "tailwindcss-macos-arm64": "cdf646702987a743464dff4d9c60fd4480d1c1e73dd819a9a67f1078815dce9d",
    "tailwindcss-macos-x64": "7922e0953f2110c05976e3bf58f14e643d90427575e766b7d433f5f80cbee7e1",
}

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "zebra-agent-web"
INPUT = WEB_DIR / "static" / "css" / "src" / "app.css"
OUTPUT = WEB_DIR / "static" / "css" / "app.css"


class BuildError(Exception):
    """Raised when the Tailwind binary cannot be obtained or verified."""


def asset_name(system: str | None = None, machine: str | None = None) -> str:
    """Return the Tailwind release asset name for a platform."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    os_part = {"linux": "linux", "darwin": "macos"}.get(system)
    arch = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(machine)
    name = f"tailwindcss-{os_part}-{arch}"
    if os_part is None or arch is None or name not in SHA256:
        raise BuildError(f"No pinned Tailwind binary for {system}/{machine}")
    return name


def verify(path: Path, expected: str) -> None:
    """Raise BuildError unless ``path`` has the expected sha256."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise BuildError(f"Checksum mismatch for {path.name}: got {digest}, expected {expected}")


def ensure_binary(cache_dir: Path | None = None) -> Path:
    """Return a verified Tailwind binary, downloading it if needed."""
    name = asset_name()
    cache_dir = (
        cache_dir
        or Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        / "zebra"
        / "tailwindcss"
        / TAILWIND_VERSION
    )
    binary = cache_dir / name
    if binary.exists():
        verify(binary, SHA256[name])
        return binary

    cache_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/tailwindlabs/tailwindcss/releases/download/{TAILWIND_VERSION}/{name}"
    print(f"Downloading {url}", file=sys.stderr)
    with tempfile.NamedTemporaryFile(dir=cache_dir, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                tmp.write(resp.read())
        except OSError as exc:  # URLError, timeouts and connection resets are all OSError
            tmp.close()
            tmp_path.unlink(missing_ok=True)
            raise BuildError(
                f"Could not download {url}: {exc}. Check network access, or copy the "
                f"binary into {cache_dir} by hand (it is checksum-verified on use)."
            ) from exc
    try:
        verify(tmp_path, SHA256[name])
    except BuildError:
        tmp_path.unlink(missing_ok=True)
        raise
    tmp_path.chmod(tmp_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    tmp_path.replace(binary)
    return binary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--watch", action="store_true", help="rebuild when sources change")
    args = parser.parse_args(argv)

    try:
        binary = ensure_binary()
    except BuildError as exc:
        print(f"build_css: {exc}", file=sys.stderr)
        return 1

    cmd = [str(binary), "--input", str(INPUT), "--output", str(OUTPUT)]
    cmd.append("--watch" if args.watch else "--minify")
    return subprocess.call(cmd, cwd=WEB_DIR)


if __name__ == "__main__":
    sys.exit(main())
