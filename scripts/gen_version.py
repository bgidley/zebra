"""Generate version.json for the Docker image.

Run from the repo root: python scripts/gen_version.py > version.json
"""

import json
import subprocess
import sys


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def main() -> None:
    try:
        short_hash = _git("log", "-1", "--pretty=format:%h")
        date = _git("log", "-1", "--pretty=format:%cd", "--date=short")
        log_lines = _git(
            "log",
            "master",
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
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"gen_version: warning: {exc}", file=sys.stderr)
        short_hash, date, commits = "unknown", "", []

    json.dump({"short_hash": short_hash, "date": date, "commits": commits}, sys.stdout, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
