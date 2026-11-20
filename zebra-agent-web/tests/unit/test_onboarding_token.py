"""Onboarding resume tokens, nonce storage and log redaction (#276)."""

from __future__ import annotations

import logging

import pytest
from django.core import signing
from zebra_agent_web.api import onboarding as ob
from zebra_agent_web.logging_filters import RedactSecretsFilter, redact


def test_token_round_trip():
    token = ob.make_token("p-1", "n-1")
    assert ob.read_token(token) == ("p-1", "n-1")


@pytest.mark.parametrize(
    "token",
    [None, "", "garbage", signing.dumps({"p": "p-1", "n": "n-1"}, salt="another.salt")],
)
def test_bad_or_foreign_tokens_are_rejected(token):
    assert ob.read_token(token) is None


def test_tampered_token_is_rejected():
    token = ob.make_token("p-1", "n-1")
    payload, _, signature = token.rpartition(":")
    assert ob.read_token(f"{payload}:{signature[:-2]}xx") is None


def test_token_expires(settings, monkeypatch):
    token = ob.make_token("p-1", "n-1")
    monkeypatch.setattr(ob, "max_age_seconds", lambda: -1)
    assert ob.read_token(token) is None


def test_token_without_nonce_is_rejected():
    assert ob.read_token(signing.dumps({"p": "p-1", "n": ""}, salt=ob.TOKEN_SALT)) is None


def test_only_the_hash_of_the_nonce_is_stored():
    nonce = ob.new_nonce()
    assert len(nonce) >= 40
    assert ob.nonce_hash(nonce) != nonce
    assert len(ob.nonce_hash(nonce)) == 64


@pytest.mark.django_db(transaction=True)
async def test_load_session_needs_the_matching_nonce(onboarding_env):
    engine, library = onboarding_env
    process, nonce = await ob.start_session(engine, library)

    assert (await ob.load_session(engine.store, ob.make_token(process.id, nonce))).id == process.id
    assert await ob.load_session(engine.store, ob.make_token(process.id, "other")) is None
    assert await ob.load_session(engine.store, ob.make_token("no-such-process", nonce)) is None
    # The process holds the hash, never the nonce or the token
    stored = (await engine.store.load_process(process.id)).properties
    assert stored[ob.NONCE_KEY] == ob.nonce_hash(nonce)
    assert nonce not in str(stored)


@pytest.mark.django_db(transaction=True)
async def test_a_non_onboarding_process_cannot_be_resumed(onboarding_env):
    from zebra.core.models import ProcessDefinition, TaskDefinition

    engine, _ = onboarding_env
    definition = ProcessDefinition(
        id="other",
        name="Other",
        first_task_id="t",
        tasks={"t": TaskDefinition(id="t", name="T", auto=False)},
        routings=[],
    )
    nonce = ob.new_nonce()
    process = await engine.create_process(
        definition, properties={ob.NONCE_KEY: ob.nonce_hash(nonce)}
    )
    assert await ob.load_session(engine.store, ob.make_token(process.id, nonce)) is None


@pytest.mark.django_db(transaction=True)
async def test_rotating_the_nonce_invalidates_old_tokens(onboarding_env):
    engine, library = onboarding_env
    process, old = await ob.start_session(engine, library)
    new = await ob.rotate_nonce(engine.store, process.id)

    assert await ob.load_session(engine.store, ob.make_token(process.id, old)) is None
    assert (await ob.load_session(engine.store, ob.make_token(process.id, new))).id == process.id


# ---------------------------------------------------------------------------
# Log redaction
# ---------------------------------------------------------------------------


def test_redact_masks_resume_links_cookies_and_token_values():
    token = ob.make_token("p-1", "secret-nonce")
    line = (
        f'"GET /onboarding/r/{token}/ HTTP/1.1" cookie zebra_onboarding={token}; '
        f"token={token} nonce: secret-nonce resume_token='{token}'"
    )
    out = redact(line)
    assert token not in out
    assert "secret-nonce" not in out
    assert "/onboarding/r/[redacted]/" in out


def test_redact_keeps_token_counts():
    line = "tokens_used=1234 total_tokens: 99 input_tokens=5"
    assert redact(line) == line


def test_filter_rewrites_records_with_args():
    token = ob.make_token("p-1", "n-1")
    record = logging.LogRecord(
        "x", logging.WARNING, __file__, 1, "Not Found: %s", (f"/onboarding/r/{token}/",), None
    )
    assert RedactSecretsFilter().filter(record) is True
    assert token not in record.getMessage()


def test_every_configured_handler_redacts():
    from django.conf import settings

    handlers = settings.LOGGING["handlers"]
    assert handlers and all("redact_secrets" in h.get("filters", []) for h in handlers.values())


def test_the_structlog_root_handler_redacts():
    from zebra_agent_web.logging_config import configure_logging

    root = logging.getLogger()
    saved, level = list(root.handlers), root.level
    try:
        configure_logging(json_logs=True)
        [handler] = root.handlers
        assert any(isinstance(f, RedactSecretsFilter) for f in handler.filters)
    finally:
        root.handlers, root.level = saved, level
