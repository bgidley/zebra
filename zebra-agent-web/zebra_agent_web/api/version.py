"""Git version metadata loaded from version.json at startup."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_FALLBACK: dict = {"short_hash": "unknown", "date": "", "commits": []}

_VERSION: dict = {}


def load_version(path: Path | None = None) -> dict:
    """Read version.json and return its contents, falling back to unknown on any error."""
    if path is None:
        # version.json sits at the repo root, one level above zebra-agent-web/
        path = Path(__file__).resolve().parents[3] / "version.json"
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError("version.json root must be a JSON object")
        return data
    except FileNotFoundError:
        logger.debug("version.json not found at %s — using fallback", path)
        return dict(_FALLBACK)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("version.json malformed (%s) — using fallback", exc)
        return dict(_FALLBACK)


_VERSION.update(load_version())
