"""Email notification task action (SMTP)."""

import asyncio
import logging
import os
import smtplib
from email.message import EmailMessage

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 30
_SECURITY_MODES = ("starttls", "ssl", "none")


def _split_addresses(value: str | list[str] | None) -> list[str]:
    """Normalise a comma-separated string or list into a list of addresses."""
    if not value:
        return []
    items = value if isinstance(value, list) else str(value).split(",")
    return [str(item).strip() for item in items if str(item).strip()]


def _send(
    message: EmailMessage,
    host: str,
    port: int,
    security: str,
    username: str | None,
    password: str | None,
) -> None:
    """Send a message synchronously. Runs in a worker thread."""
    smtp_class = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
    with smtp_class(host, port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
        if security == "starttls":
            smtp.starttls()
        if username:
            smtp.login(username, password or "")
        smtp.send_message(message)


class NotifyEmailAction(TaskAction):
    """Send an email notification over SMTP.

    Server settings come from environment variables:
    ``ZEBRA_SMTP_HOST`` (required), ``ZEBRA_SMTP_PORT`` (default 587),
    ``ZEBRA_SMTP_SECURITY`` (``starttls`` | ``ssl`` | ``none``, default ``starttls``),
    ``ZEBRA_SMTP_USERNAME`` / ``ZEBRA_SMTP_PASSWORD`` (login only if a username is set)
    and ``ZEBRA_SMTP_FROM`` (defaults to the username). Recipients default to
    ``ZEBRA_NOTIFY_EMAIL_TO`` (comma-separated).

    Example workflow usage:
        ```yaml
        tasks:
          notify:
            name: "Email the digest"
            action: notify_email
            properties:
              subject: "Daily digest: {{topic}}"
              body: "{{digest}}"
        ```

    Output:
        - to: list of recipient addresses
        - subject: the resolved subject line
    """

    description = "Send an email notification over SMTP."
    reversibility_hint = "always_irreversible"

    inputs = [
        ParameterDef(
            name="to",
            type="string",
            description="Recipient(s): comma-separated string or list; "
            "defaults to ZEBRA_NOTIFY_EMAIL_TO",
            required=False,
        ),
        ParameterDef(
            name="subject",
            type="string",
            description="Subject line (supports {{var}} templates)",
            required=True,
        ),
        ParameterDef(
            name="body",
            type="string",
            description="Plain-text body (supports {{var}} templates)",
            required=True,
        ),
        ParameterDef(
            name="html",
            type="string",
            description="Optional HTML alternative body (supports {{var}} templates)",
            required=False,
        ),
    ]

    outputs = [
        ParameterDef(name="to", type="list", description="Recipient addresses", required=True),
        ParameterDef(name="subject", type="string", description="Subject sent", required=True),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Build and send the email."""
        host = os.environ.get("ZEBRA_SMTP_HOST")
        if not host:
            return TaskResult.fail("ZEBRA_SMTP_HOST environment variable is not set")

        security = os.environ.get("ZEBRA_SMTP_SECURITY", "starttls").lower()
        if security not in _SECURITY_MODES:
            return TaskResult.fail(
                f"ZEBRA_SMTP_SECURITY must be one of {', '.join(_SECURITY_MODES)}"
            )
        try:
            port = int(os.environ.get("ZEBRA_SMTP_PORT", "587"))
        except ValueError:
            return TaskResult.fail("ZEBRA_SMTP_PORT must be an integer")

        username = os.environ.get("ZEBRA_SMTP_USERNAME")
        password = os.environ.get("ZEBRA_SMTP_PASSWORD")
        sender = os.environ.get("ZEBRA_SMTP_FROM") or username
        if not sender:
            return TaskResult.fail("Set ZEBRA_SMTP_FROM (or ZEBRA_SMTP_USERNAME) for the sender")

        to_value = task.properties.get("to")
        if isinstance(to_value, str):
            to_value = context.resolve_template(to_value)
        recipients = _split_addresses(to_value) or _split_addresses(
            os.environ.get("ZEBRA_NOTIFY_EMAIL_TO")
        )
        if not recipients:
            return TaskResult.fail("No recipient: set 'to' or ZEBRA_NOTIFY_EMAIL_TO")

        subject_template = task.properties.get("subject")
        body_template = task.properties.get("body")
        if not subject_template or body_template is None:
            return TaskResult.fail("Both 'subject' and 'body' are required")
        subject = context.resolve_template(str(subject_template)).strip()

        message = EmailMessage()
        message["From"] = sender
        message["To"] = ", ".join(recipients)
        message["Subject"] = subject
        message.set_content(context.resolve_template(str(body_template)))
        html_template = task.properties.get("html")
        if html_template:
            message.add_alternative(context.resolve_template(str(html_template)), subtype="html")

        try:
            await asyncio.to_thread(_send, message, host, port, security, username, password)
        except (smtplib.SMTPException, OSError) as e:
            error = str(e)
            if password:
                error = error.replace(password, "***")
            logger.warning("Email notification to %s failed: %s", recipients, error)
            return TaskResult.fail(f"SMTP error sending email: {error}")

        logger.info("Email notification sent to %s: %s", recipients, subject)
        return TaskResult.ok(output={"to": recipients, "subject": subject})
