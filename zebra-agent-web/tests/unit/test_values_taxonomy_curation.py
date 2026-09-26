"""Tests for values-taxonomy curation (#106): lifecycle, merge, prune, command, page."""

from __future__ import annotations

import uuid
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from zebra_agent_web import values_taxonomy as taxonomy
from zebra_agent_web.api.models import ValuesTagModel
from zebra_agent_web.profile_store import DjangoProfileStore

FIELD = "core_values"


def _tag(slug: str, status: str = "candidate", usage: int = 1, field: str = FIELD, **kw):
    return ValuesTagModel.objects.create(
        id=str(uuid.uuid4()),
        field=field,
        slug=slug,
        label=slug.replace("-", " ").title(),
        status=status,
        usage_count=usage,
        **kw,
    )


def _get(slug: str, field: str = FIELD) -> ValuesTagModel:
    return ValuesTagModel.objects.get(field=field, slug=slug)


# --- lifecycle ---------------------------------------------------------------


@pytest.mark.django_db
def test_promote_candidate_sets_promoted_at_and_joins_approved_set() -> None:
    _tag("t106-curiosity")

    view = taxonomy.promote(FIELD, "t106-curiosity")

    assert view.status == "promoted"
    row = _get("t106-curiosity")
    assert row.promoted_at is not None
    approved = ValuesTagModel.objects.filter(field=FIELD, status__in=["seeded", "promoted"])
    assert approved.filter(slug="t106-curiosity").exists()


@pytest.mark.django_db
def test_reject_then_promote_rejected_tag() -> None:
    _tag("t106-gaming")

    assert taxonomy.reject(FIELD, "t106-gaming").status == "rejected"
    assert taxonomy.promote(FIELD, "t106-gaming").status == "promoted"


@pytest.mark.django_db
def test_demote_promoted_clears_promoted_at() -> None:
    _tag("t106-grit", status="promoted", promoted_at=timezone.now())

    view = taxonomy.demote(FIELD, "t106-grit")

    assert view.status == "candidate"
    assert _get("t106-grit").promoted_at is None


@pytest.mark.django_db
def test_archive_promoted_via_reject() -> None:
    _tag("t106-old", status="promoted", promoted_at=timezone.now())

    assert taxonomy.reject(FIELD, "t106-old").status == "rejected"


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["promote", "reject", "demote"])
def test_seeded_tags_cannot_be_curated(operation: str) -> None:
    _tag("t106-seed", status="seeded")

    with pytest.raises(taxonomy.TaxonomyError):
        getattr(taxonomy, operation)(FIELD, "t106-seed")
    assert _get("t106-seed").status == "seeded"


@pytest.mark.django_db
def test_demote_candidate_is_refused() -> None:
    _tag("t106-cand")

    with pytest.raises(taxonomy.TaxonomyError, match="Cannot demote"):
        taxonomy.demote(FIELD, "t106-cand")
    assert _get("t106-cand").status == "candidate"


@pytest.mark.django_db
def test_unknown_tag_and_field_are_refused() -> None:
    with pytest.raises(taxonomy.TaxonomyError, match="No tag"):
        taxonomy.promote(FIELD, "t106-missing")
    with pytest.raises(taxonomy.TaxonomyError, match="Unknown field"):
        taxonomy.promote("hobbies", "anything")


# --- merge -------------------------------------------------------------------


@pytest.mark.django_db
def test_merge_moves_usage_and_marks_source_merged() -> None:
    _tag("t106-truthfulness", usage=4)
    _tag("t106-honesty", status="seeded", usage=2)

    target = taxonomy.merge(FIELD, "t106-truthfulness", "t106-honesty")

    assert target.slug == "t106-honesty"
    assert target.usage_count == 6
    source = _get("t106-truthfulness")
    assert source.status == "merged"
    assert source.merged_into == "t106-honesty"
    assert source.usage_count == 0


@pytest.mark.django_db
def test_merge_repoints_earlier_merges_to_avoid_chains() -> None:
    _tag("t106-a", status="merged", usage=0, merged_into="t106-b")
    _tag("t106-b", usage=3)
    _tag("t106-c", status="promoted", usage=1)

    taxonomy.merge(FIELD, "t106-b", "t106-c")

    assert _get("t106-a").merged_into == "t106-c"
    assert _get("t106-b").merged_into == "t106-c"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("t106-src", "t106-src"),  # self
        ("t106-src", "t106-missing"),  # missing target
        ("t106-src", "t106-rejected"),  # rejected target
        ("t106-src", "t106-merged"),  # merged target
        ("t106-seeded", "t106-src"),  # seeded source
    ],
)
def test_invalid_merges_change_nothing(source: str, target: str) -> None:
    _tag("t106-src", usage=2)
    _tag("t106-rejected", status="rejected", usage=1)
    _tag("t106-merged", status="merged", usage=0, merged_into="t106-src")
    _tag("t106-seeded", status="seeded", usage=5)

    with pytest.raises(taxonomy.TaxonomyError):
        taxonomy.merge(FIELD, source, target)

    assert _get("t106-src").status == "candidate"
    assert _get("t106-src").usage_count == 2
    assert _get("t106-seeded").usage_count == 5


@pytest.mark.django_db
def test_merge_across_fields_is_refused() -> None:
    _tag("t106-family", field="core_values")
    _tag("t106-kin", field="priorities")

    with pytest.raises(taxonomy.TaxonomyError, match="No tag"):
        taxonomy.merge("core_values", "t106-family", "t106-kin")


@pytest.mark.django_db(transaction=True)
async def test_confirming_merged_slug_counts_toward_target() -> None:
    from asgiref.sync import sync_to_async

    await sync_to_async(_tag)("t106-truthful", status="merged", usage=0, merged_into="t106-honest")
    await sync_to_async(_tag)("t106-honest", status="promoted", usage=2)

    await DjangoProfileStore().record_confirmed_tags(
        {FIELD: [{"slug": "t106-truthful", "label": "Truthful"}]}
    )

    source = await sync_to_async(_get)("t106-truthful")
    target = await sync_to_async(_get)("t106-honest")
    assert (source.status, source.usage_count) == ("merged", 0)
    assert target.usage_count == 3


@pytest.mark.django_db(transaction=True)
async def test_confirming_rejected_tag_keeps_it_rejected() -> None:
    from asgiref.sync import sync_to_async

    await sync_to_async(_tag)("t106-noise", status="rejected", usage=1)

    await DjangoProfileStore().record_confirmed_tags({FIELD: [{"slug": "t106-noise"}]})

    row = await sync_to_async(_get)("t106-noise")
    assert (row.status, row.usage_count) == ("rejected", 2)


# --- suggestions & prune -----------------------------------------------------


@pytest.mark.django_db
def test_suggested_uses_threshold_and_does_not_promote(settings) -> None:
    settings.ZEBRA_AGENT_SETTINGS = {**settings.ZEBRA_AGENT_SETTINGS}
    settings.ZEBRA_AGENT_SETTINGS["VALUES_TAG_PROMOTION_THRESHOLD"] = 3
    _tag("t106-hot", usage=3)
    _tag("t106-cold", usage=2)

    suggested = {t.slug for t in taxonomy.list_tags(suggested_only=True)}

    assert "t106-hot" in suggested
    assert "t106-cold" not in suggested
    assert _get("t106-hot").status == "candidate"


def _age(slug: str, days: int) -> None:
    ValuesTagModel.objects.filter(slug=slug).update(
        created_at=timezone.now() - timedelta(days=days)
    )


@pytest.mark.django_db
def test_prune_only_removes_stale_low_usage_candidates() -> None:
    for slug, status, usage, age in [
        ("t106-stale", "candidate", 1, 120),
        ("t106-fresh", "candidate", 1, 5),
        ("t106-popular", "candidate", 5, 120),
        ("t106-rejected-old", "rejected", 1, 120),
    ]:
        _tag(slug, status=status, usage=usage)
        _age(slug, age)

    dry = taxonomy.prune(days=90, max_usage=1, dry_run=True)
    assert [t.slug for t in dry] == ["t106-stale"]
    assert ValuesTagModel.objects.filter(slug="t106-stale").exists()

    deleted = taxonomy.prune(days=90, max_usage=1)
    assert [t.slug for t in deleted] == ["t106-stale"]
    remaining = set(
        ValuesTagModel.objects.filter(slug__startswith="t106-").values_list("slug", flat=True)
    )
    assert remaining == {"t106-fresh", "t106-popular", "t106-rejected-old"}


# --- management command ------------------------------------------------------


@pytest.mark.django_db
def test_command_promote_and_list() -> None:
    _tag("t106-cmd", usage=4)
    out = StringIO()

    call_command("values_taxonomy", "promote", FIELD, "t106-cmd", stdout=out)
    call_command("values_taxonomy", "list", "--status", "promoted", stdout=out)

    assert "core_values/t106-cmd is now promoted" in out.getvalue()
    assert "t106-cmd" in out.getvalue().split("now promoted", 1)[1]


@pytest.mark.django_db
def test_command_merge_and_invalid_operation() -> None:
    _tag("t106-x", usage=1)
    _tag("t106-y", usage=1)
    out = StringIO()

    call_command("values_taxonomy", "merge", FIELD, "t106-x", "t106-y", stdout=out)
    assert "Merged t106-x into t106-y" in out.getvalue()

    with pytest.raises(CommandError, match="Cannot demote"):
        call_command("values_taxonomy", "demote", FIELD, "t106-y")


@pytest.mark.django_db
def test_command_prune_dry_run() -> None:
    _tag("t106-dusty")
    _age("t106-dusty", 200)
    out = StringIO()

    call_command("values_taxonomy", "prune", "--dry-run", stdout=out)

    assert "Would delete 1 stale candidate tag(s)" in out.getvalue()
    assert ValuesTagModel.objects.filter(slug="t106-dusty").exists()


# --- web page ----------------------------------------------------------------


@pytest.fixture
def completed_setup(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.mark.django_db(transaction=True)
async def test_taxonomy_page_lists_candidates(authenticated_async_client, completed_setup) -> None:
    from asgiref.sync import sync_to_async

    await sync_to_async(_tag)("t106-page", usage=9)

    response = await authenticated_async_client.get("/profile/taxonomy/")

    assert response.status_code == 200
    body = response.content.decode()
    assert 'data-testid="candidate-t106-page"' in body
    assert "suggested" in body


@pytest.mark.django_db(transaction=True)
async def test_taxonomy_action_promotes_and_redirects(
    authenticated_async_client, completed_setup
) -> None:
    from asgiref.sync import sync_to_async

    await sync_to_async(_tag)("t106-web")

    response = await authenticated_async_client.post(
        "/profile/taxonomy/action/",
        {"action": "promote", "field": FIELD, "slug": "t106-web"},
    )

    assert response.status_code == 302
    assert "message=" in response["Location"]
    assert (await sync_to_async(_get)("t106-web")).status == "promoted"


@pytest.mark.django_db(transaction=True)
async def test_taxonomy_action_error_redirects_with_error(
    authenticated_async_client, completed_setup
) -> None:
    response = await authenticated_async_client.post(
        "/profile/taxonomy/action/",
        {"action": "promote", "field": FIELD, "slug": "t106-nope"},
    )

    assert response.status_code == 302
    assert "error=" in response["Location"]
