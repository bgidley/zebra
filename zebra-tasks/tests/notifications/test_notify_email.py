"""Tests for NotifyEmailAction."""

import smtplib
from unittest.mock import MagicMock, patch

import pytest
from zebra.core.models import TaskInstance, TaskState

from zebra_tasks.notifications.smtp_email import NotifyEmailAction

MODULE = "zebra_tasks.notifications.smtp_email"


def make_task(properties: dict) -> TaskInstance:
    return TaskInstance(
        id="task-1",
        process_id="proc-1",
        task_definition_id="notify",
        state=TaskState.RUNNING,
        foe_id="foe-1",
        properties=properties,
    )


@pytest.fixture
def action():
    return NotifyEmailAction()


@pytest.fixture
def smtp_env(monkeypatch):
    for name in ("ZEBRA_SMTP_PORT", "ZEBRA_SMTP_SECURITY", "ZEBRA_NOTIFY_EMAIL_TO"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ZEBRA_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("ZEBRA_SMTP_USERNAME", "zebra@example.com")
    monkeypatch.setenv("ZEBRA_SMTP_PASSWORD", "s3cret-pw")
    monkeypatch.delenv("ZEBRA_SMTP_FROM", raising=False)


def smtp_mock() -> MagicMock:
    """A mock SMTP class whose instance works as a context manager."""
    smtp_class = MagicMock()
    server = smtp_class.return_value
    server.__enter__.return_value = server
    server.__exit__.return_value = False
    return smtp_class


async def test_sends_email_with_resolved_templates(action, mock_context, smtp_env):
    mock_context.process.properties["topic"] = "zebras"
    mock_context.process.properties["digest"] = "Three new papers."
    smtp_class = smtp_mock()
    task = make_task(
        {"to": "ben@example.com", "subject": "Digest: {{topic}}", "body": "{{digest}}"}
    )

    with patch(f"{MODULE}.smtplib.SMTP", smtp_class):
        result = await action.run(task, mock_context)

    assert result.success
    assert result.output == {"to": ["ben@example.com"], "subject": "Digest: zebras"}
    smtp_class.assert_called_once_with("smtp.example.com", 587, timeout=30)
    server = smtp_class.return_value
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("zebra@example.com", "s3cret-pw")
    message = server.send_message.call_args.args[0]
    assert message["To"] == "ben@example.com"
    assert message["From"] == "zebra@example.com"
    assert message["Subject"] == "Digest: zebras"
    assert message.get_content().strip() == "Three new papers."


async def test_defaults_recipients_from_env(action, mock_context, smtp_env, monkeypatch):
    monkeypatch.setenv("ZEBRA_NOTIFY_EMAIL_TO", "a@example.com, b@example.com")
    smtp_class = smtp_mock()

    with patch(f"{MODULE}.smtplib.SMTP", smtp_class):
        result = await action.run(make_task({"subject": "Hi", "body": "Hello"}), mock_context)

    assert result.success
    assert result.output["to"] == ["a@example.com", "b@example.com"]
    message = smtp_class.return_value.send_message.call_args.args[0]
    assert message["To"] == "a@example.com, b@example.com"


async def test_accepts_list_of_recipients(action, mock_context, smtp_env):
    smtp_class = smtp_mock()
    task = make_task({"to": ["a@example.com", "b@example.com"], "subject": "Hi", "body": "x"})

    with patch(f"{MODULE}.smtplib.SMTP", smtp_class):
        result = await action.run(task, mock_context)

    assert result.output["to"] == ["a@example.com", "b@example.com"]


async def test_html_alternative(action, mock_context, smtp_env):
    smtp_class = smtp_mock()
    task = make_task({"to": "a@example.com", "subject": "Hi", "body": "plain", "html": "<b>x</b>"})

    with patch(f"{MODULE}.smtplib.SMTP", smtp_class):
        await action.run(task, mock_context)

    message = smtp_class.return_value.send_message.call_args.args[0]
    assert message.is_multipart()
    assert message.get_body(("html",)).get_content().strip() == "<b>x</b>"


async def test_ssl_mode_uses_smtp_ssl(action, mock_context, smtp_env, monkeypatch):
    monkeypatch.setenv("ZEBRA_SMTP_SECURITY", "ssl")
    monkeypatch.setenv("ZEBRA_SMTP_PORT", "465")
    ssl_class = smtp_mock()
    plain_class = smtp_mock()

    with (
        patch(f"{MODULE}.smtplib.SMTP_SSL", ssl_class),
        patch(f"{MODULE}.smtplib.SMTP", plain_class),
    ):
        result = await action.run(
            make_task({"to": "a@example.com", "subject": "s", "body": "b"}), mock_context
        )

    assert result.success
    ssl_class.assert_called_once_with("smtp.example.com", 465, timeout=30)
    ssl_class.return_value.starttls.assert_not_called()
    plain_class.assert_not_called()


async def test_no_auth_when_no_username(action, mock_context, smtp_env, monkeypatch):
    monkeypatch.delenv("ZEBRA_SMTP_USERNAME")
    monkeypatch.setenv("ZEBRA_SMTP_FROM", "noreply@example.com")
    monkeypatch.setenv("ZEBRA_SMTP_SECURITY", "none")
    smtp_class = smtp_mock()

    with patch(f"{MODULE}.smtplib.SMTP", smtp_class):
        result = await action.run(
            make_task({"to": "a@example.com", "subject": "s", "body": "b"}), mock_context
        )

    assert result.success
    smtp_class.return_value.login.assert_not_called()
    smtp_class.return_value.starttls.assert_not_called()


async def test_fails_when_host_not_configured(action, mock_context, smtp_env, monkeypatch):
    monkeypatch.delenv("ZEBRA_SMTP_HOST")
    smtp_class = smtp_mock()

    with patch(f"{MODULE}.smtplib.SMTP", smtp_class):
        result = await action.run(
            make_task({"to": "a@example.com", "subject": "s", "body": "b"}), mock_context
        )

    assert not result.success
    assert "ZEBRA_SMTP_HOST" in result.error
    smtp_class.assert_not_called()


async def test_fails_without_recipient(action, mock_context, smtp_env):
    smtp_class = smtp_mock()

    with patch(f"{MODULE}.smtplib.SMTP", smtp_class):
        result = await action.run(make_task({"subject": "s", "body": "b"}), mock_context)

    assert not result.success
    assert "recipient" in result.error
    smtp_class.assert_not_called()


async def test_fails_without_subject(action, mock_context, smtp_env):
    result = await action.run(make_task({"to": "a@example.com", "body": "b"}), mock_context)
    assert not result.success


async def test_rejects_unknown_security_mode(action, mock_context, smtp_env, monkeypatch):
    monkeypatch.setenv("ZEBRA_SMTP_SECURITY", "tls1.0")
    result = await action.run(
        make_task({"to": "a@example.com", "subject": "s", "body": "b"}), mock_context
    )
    assert not result.success
    assert "ZEBRA_SMTP_SECURITY" in result.error


async def test_smtp_error_fails_without_leaking_password(action, mock_context, smtp_env):
    smtp_class = smtp_mock()
    smtp_class.return_value.login.side_effect = smtplib.SMTPAuthenticationError(
        535, b"bad credentials for s3cret-pw"
    )

    with patch(f"{MODULE}.smtplib.SMTP", smtp_class):
        result = await action.run(
            make_task({"to": "a@example.com", "subject": "s", "body": "b"}), mock_context
        )

    assert not result.success
    assert "SMTP error" in result.error
    assert "s3cret-pw" not in result.error


async def test_connection_error_fails(action, mock_context, smtp_env):
    smtp_class = MagicMock(side_effect=ConnectionRefusedError("refused"))

    with patch(f"{MODULE}.smtplib.SMTP", smtp_class):
        result = await action.run(
            make_task({"to": "a@example.com", "subject": "s", "body": "b"}), mock_context
        )

    assert not result.success
    assert "refused" in result.error


def test_metadata_declares_irreversible():
    metadata = NotifyEmailAction.get_metadata()
    assert metadata.reversibility_hint == "always_irreversible"
    assert metadata.description
