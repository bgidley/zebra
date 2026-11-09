"""Generate version.json for the Docker image.

Run from the repo root: python scripts/gen_version.py > version.json

``version`` comes from the newest ``vX.Y.Z`` release tag reachable from HEAD (#283):
``0.3.0`` on the tag itself, ``0.3.0+4.gabc1234`` four commits after it, and
``0.0.0+gabc1234`` before the first release. CI checkouts are shallow and may not carry
tags, so when no tag is found in a shallow clone the script fetches tags and history once
(best effort) before giving up.
"""

import json
import re
import subprocess
import sys

TAG_PATTERN = "v[0-9]*.[0-9]*.[0-9]*"
_DESCRIBE_RE = re.compile(r"^v(\d+\.\d+\.\d+)(?:-(\d+)-g([0-9a-f]+))?$")


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def version_from_describe(describe: str | None, short_hash: str) -> str:
    """Turn ``git describe --tags --long`` output into a semver-style version string.

    Args:
        describe: Output of ``git describe``, e.g. ``v0.3.0-4-gabc1234``; None when no tag.
        short_hash: Short commit hash, used when there is no release tag yet.

    Returns:
        ``0.3.0`` on a tag, ``0.3.0+4.gabc1234`` after it, ``0.0.0+g<hash>`` before any tag.
    """
    match = _DESCRIBE_RE.match(describe or "")
    if not match:
        return f"0.0.0+g{short_hash}"
    base, distance, sha = match.groups()
    if not distance or distance == "0":
        return base
    return f"{base}+{distance}.g{sha}"


def _describe() -> str | None:
    try:
        return _git("describe", "--tags", "--long", "--match", TAG_PATTERN, "HEAD")
    except subprocess.CalledProcessError:
        return None


def describe_release() -> str | None:
    """Describe HEAD against release tags, deepening a shallow CI clone once if needed."""
    found = _describe()
    if found is not None:
        return found
    try:
        shallow = _git("rev-parse", "--is-shallow-repository") == "true"
    except subprocess.CalledProcessError:
        return None
    if not shallow:
        return None
    try:
        subprocess.run(
            ["git", "fetch", "--quiet", "--tags", "--unshallow", "origin"],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"gen_version: warning: could not fetch tags: {exc}", file=sys.stderr)
        return None
    return _describe()


def main() -> None:
    try:
        short_hash = _git("log", "-1", "--pretty=format:%h")
        date = _git("log", "-1", "--pretty=format:%cd", "--date=short")
        log_lines = _git(
            "log",
            "HEAD",
            "-10",
            "--pretty=format:%h\t%cd\t%s",
            "--date=short",
        ).splitlines()
        commits = [
            {"hash": h, "date": d, "subject": s}
            for line in log_lines
            if line.strip()
            for h, d, s in [line.split("\t", 2)]
        ]
        version = version_from_describe(describe_release(), short_hash)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"gen_version: warning: {exc}", file=sys.stderr)
        short_hash, date, commits, version = "unknown", "", [], "unknown"

    json.dump(
        {"version": version, "short_hash": short_hash, "date": date, "commits": commits},
        sys.stdout,
        indent=2,
    )
    print()  # trailing newline


if __name__ == "__main__":
    main()
