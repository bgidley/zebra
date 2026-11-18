"""Link-check the external hrefs in the onboarding templates (#277).

Usage: uv run python scripts/check_onboarding_links.py
Exit 1 if any link does not answer 2xx/3xx. Run by hand: Oracle's docs move.
"""

from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "zebra-agent-web" / "templates" / "pages"


def main() -> int:
    urls = sorted(
        {
            u
            for f in TEMPLATES.glob("onboarding_*.html")
            for u in re.findall(r'href="(https://[^"]+)"', f.read_text())
        }
    )
    bad = 0
    for url in urls:
        req = urllib.request.Request(url, headers={"User-Agent": "link-check"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
                status = resp.status
        except Exception as exc:
            status = getattr(exc, "code", repr(exc))
        ok = isinstance(status, int) and status < 400
        bad += not ok
        print(("OK  " if ok else "FAIL"), status, url)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
