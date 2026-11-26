"""Tell the owner something needs them, outside any workflow (#335).

``notify_owner`` is for code that is not a task action (an LLM provider, say) and
must reach the owner: an expired AWS session that stops every goal, for example.
It uses the same configuration as the ``notify_webhook`` / ``notify_email`` actions:

- ``ZEBRA_NOTIFY_WEBHOOK_URL``: POSTed ``{"subject": ..., "body": ...}`` as JSON
- ``ZEBRA_SMTP_HOST`` + ``ZEBRA_NOTIFY_EMAIL_TO``: an email (the other ``ZEBRA_SMTP_*``
  settings as for ``notify_email``)

It always logs the notice at ERROR, sends each *key* at most once per
:data:`REPEAT_AFTER_SECONDS`, and never raises.
"""

import asyncio
import logging
import os
import smtplib
import time
from email.message import EmailMessage

import httpx

from zebra_tasks.notifications.smtp_email import _send, _split_addresses

logger = logging.getLogger(__name__)

#: A notice with the same key is not sent again for this long.
REPEAT_AFTER_SECONDS = 3600.0
WEBHOOK_TIMEOUT_SECONDS = 10.0

_last_sent: dict[str, float] = {}


async def notify_owner(key: str, subject: str, body: str) -> list[str]:
    """Send *subject* / *body* to the owner on every configured channel.

    Returns the channels it went to (``webhook``, ``email``); empty when the notice
    was sent recently, or when no channel is configured (it is still logged).
    """
    now = time.monotonic()
    last = _last_sent.get(key)
    if last is not None and now - last < REPEAT_AFTER_SECONDS:
        return []
    _last_sent[key] = now
    logger.error("Owner notice: %s: %s", subject, body)

    sent: list[str] = []
    url = os.environ.get("ZEBRA_NOTIFY_WEBHOOK_URL")
    if url:
        try:
            async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
                response = await client.post(url, json={"subject": subject, "body": body})
            if 200 <= response.status_code < 300:
                sent.append("webhook")
            else:
                logger.warning("Owner notice webhook returned %d", response.status_code)
        except httpx.HTTPError as e:
            logger.warning("Owner notice webhook failed: %s", type(e).__name__)

    host = os.environ.get("ZEBRA_SMTP_HOST")
    recipients = _split_addresses(os.environ.get("ZEBRA_NOTIFY_EMAIL_TO"))
    if host and recipients:
        try:
            await asyncio.to_thread(_send_email, host, recipients, subject, body)
            sent.append("email")
        except (smtplib.SMTPException, OSError, ValueError) as e:
            logger.warning("Owner notice email failed: %s", type(e).__name__)
    return sent


def _send_email(host: str, recipients: list[str], subject: str, body: str) -> None:
    username = os.environ.get("ZEBRA_SMTP_USERNAME")
    sender = os.environ.get("ZEBRA_SMTP_FROM") or username
    if not sender:
        raise ValueError("no sender")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)
    _send(
        message,
        host,
        int(os.environ.get("ZEBRA_SMTP_PORT", "587")),
        os.environ.get("ZEBRA_SMTP_SECURITY", "starttls").lower(),
        username,
        os.environ.get("ZEBRA_SMTP_PASSWORD"),
    )


def reset_owner_notices() -> None:
    """Forget which notices were sent (for tests)."""
    _last_sent.clear()
