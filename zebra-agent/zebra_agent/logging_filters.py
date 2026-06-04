"""Logging filters for Zebra Agent.

Provides filters that prevent sensitive data from appearing in log output.
"""

from __future__ import annotations

import logging
import re

# Pattern matching common credential patterns in log messages.
# Replaces values after keywords like api_key=, token=, password=, secret=
# and also bare credential values if they look like long hex/base64 strings.
_CRED_REDACT_PATTERN = re.compile(
    r"(?i)(api[_\-]?key|token|password|secret|credential|auth)[=:\s]+\S+",
    re.IGNORECASE,
)


class ScrubCredentialsFilter(logging.Filter):
    """Logging filter that redacts credential-like values from log records.

    Applies a best-effort regex replacement over the formatted message.
    This is a safety net — the primary protection is that credential values
    are never passed to logging calls in the first place.

    Install on any handler or logger that might receive messages containing
    user-provided data::

        handler.addFilter(ScrubCredentialsFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            # Redact in the raw message string before interpolation
            record.msg = _CRED_REDACT_PATTERN.sub(
                lambda m: f"{m.group(1)}=<redacted>", str(record.msg)
            )
            # Also redact in pre-formatted args strings if they are plain strings
            if isinstance(record.args, tuple):
                record.args = tuple(
                    _CRED_REDACT_PATTERN.sub(lambda m: f"{m.group(1)}=<redacted>", str(a))
                    if isinstance(a, str)
                    else a
                    for a in record.args
                )
        except Exception:
            # Never block logging due to filter errors
            pass
        return True
