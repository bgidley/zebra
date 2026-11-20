"""Log redaction (#276): keep onboarding resume tokens and nonces out of every log line.

``RedactSecretsFilter`` rewrites a record's message before any handler formats it. It
masks the onboarding resume path (``/onboarding/r/<token>/``), the onboarding cookie and
``token=`` / ``nonce=`` style values. Attached to every handler in ``settings.LOGGING`` and to
the structlog handler, so a request line or an exception message cannot leak a resume link.
"""

from __future__ import annotations

import logging
import re

REDACTED = "[redacted]"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # The resume link: /onboarding/r/<signed token>/
    (re.compile(r"(/onboarding/r/)[^/\s'\"?#]+"), rf"\g<1>{REDACTED}"),
    # The resume cookie, as it would appear in a Cookie header
    (re.compile(r"(zebra_onboarding=)[^;\s'\"]+"), rf"\g<1>{REDACTED}"),
    # key=value / key: value / "key": "value" for a key ending in token or nonce (not
    # "tokens_used" and the like, so token counts stay readable)
    (
        re.compile(
            r"""(?ix)
            (\b(?:\w+_)?(?:token|nonce)["']?\s*[:=]\s*["']?)
            ([^\s"',;&}]+)
            """
        ),
        rf"\g<1>{REDACTED}",
    ),
]


def redact(text: str) -> str:
    """*text* with resume tokens, onboarding cookies and token / nonce values masked."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RedactSecretsFilter(logging.Filter):
    """Mask onboarding tokens and nonces in a record's message (never drops a record)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # a broken format string: leave it to the handler
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True
