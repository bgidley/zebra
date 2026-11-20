"""Row locks work on Oracle: no ``select_for_update()`` with ``LIMIT`` (#232).

Importing a Commons offer on prod (Oracle) failed with "LIMIT/OFFSET is not supported with
select_for_update on this database backend": ``DjangoOfferStore.set_status`` locked its row
with ``select_for_update().first()``. SQLite accepts that, so these tests switch SQLite to
Oracle's rule (``supports_select_for_update_with_limit = False``) to reproduce it.
"""

import re
from pathlib import Path

import pytest
from django.db import connection, transaction
from django.db.utils import NotSupportedError
from zebra_agent_web.api.models import WorkflowOfferModel
from zebra_agent_web.commons_offer_store import DjangoOfferStore
from zebra_agent_web.locking import first_for_update

PACKAGE = Path(__file__).resolve().parents[2] / "zebra_agent_web"
SHA = "ab" * 32


@pytest.fixture
def oracle_rule(monkeypatch):
    """Make the test database refuse FOR UPDATE with LIMIT, as Oracle does.

    SQLite has no row locks, so Django normally drops ``select_for_update()`` there and never
    checks the limit. Patched on the backend classes (every thread's connection): locks "on",
    a limit with a lock refused, and an empty FOR UPDATE clause so SQLite can run the query.
    """
    features, ops = type(connection.features), type(connection.ops)
    monkeypatch.setattr(features, "has_select_for_update", True)
    monkeypatch.setattr(features, "supports_select_for_update_with_limit", False)
    monkeypatch.setattr(ops, "for_update_sql", lambda self, *args, **kwargs: "")


def _offer() -> WorkflowOfferModel:
    return WorkflowOfferModel.objects.create(
        content_sha256=SHA, name="Answer Question", publisher_pubkey="cd" * 32, event_id="ef" * 32
    )


@pytest.mark.django_db
def test_the_old_pattern_fails_under_oracles_rule(oracle_rule):
    _offer()
    with transaction.atomic(), pytest.raises(NotSupportedError):
        WorkflowOfferModel.objects.select_for_update().filter(content_sha256=SHA).first()


@pytest.mark.django_db
def test_first_for_update_locks_without_a_limit(oracle_rule):
    row = _offer()
    with transaction.atomic():
        assert first_for_update(WorkflowOfferModel.objects.filter(content_sha256=SHA)) == row
        assert first_for_update(WorkflowOfferModel.objects.filter(content_sha256="00" * 32)) is None


@pytest.mark.django_db(transaction=True)
async def test_offer_status_changes_under_oracles_rule(oracle_rule):
    """The path behind "Import this": seen -> judging."""
    from asgiref.sync import sync_to_async

    await sync_to_async(_offer)()

    record = await DjangoOfferStore(None).set_status(SHA, "judging")

    assert record.status == "judging"


def test_no_select_for_update_with_first_or_slice():
    """Every row lock goes through ``first_for_update`` (or locks without a limit)."""
    pattern = re.compile(r"select_for_update\(\)[^;]*?\)\s*(\.first\(\)|\.last\(\)|\[)", re.S)
    offenders = [
        str(path.relative_to(PACKAGE))
        for path in PACKAGE.rglob("*.py")
        if "/migrations/" not in str(path) and pattern.search(path.read_text())
    ]
    assert not offenders, (
        f"select_for_update() with first/last/slice (fails on Oracle): {offenders}"
    )
