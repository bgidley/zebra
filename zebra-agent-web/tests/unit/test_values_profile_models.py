"""Tests for the F18 values-profile Django models."""

import uuid

import pytest
from django.db import IntegrityError
from zebra_agent_web.api.models import (
    ValuesProfileModel,
    ValuesProfileVersionModel,
    ValuesTagModel,
)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest.mark.django_db
def test_values_profile_creation():
    profile = ValuesProfileModel.objects.create(id=_new_id(), user_id=42)
    assert profile.user_id == 42
    assert profile.current_version is None
    assert profile.created_at is not None


@pytest.mark.django_db
def test_user_id_uniqueness():
    ValuesProfileModel.objects.create(id=_new_id(), user_id=42)
    with pytest.raises(IntegrityError):
        ValuesProfileModel.objects.create(id=_new_id(), user_id=42)


@pytest.mark.django_db
def test_version_creation_and_fk():
    profile = ValuesProfileModel.objects.create(id=_new_id(), user_id=1)
    version = ValuesProfileVersionModel.objects.create(
        id=_new_id(),
        profile=profile,
        version_number=1,
        core_values_text="honesty, growth",
        core_values_tags=["honesty", "growth"],
    )
    assert version.profile_id == profile.id
    assert version.version_number == 1
    assert version.core_values_tags == ["honesty", "growth"]


@pytest.mark.django_db
def test_version_default_empty_tags():
    profile = ValuesProfileModel.objects.create(id=_new_id(), user_id=1)
    version = ValuesProfileVersionModel.objects.create(
        id=_new_id(), profile=profile, version_number=1
    )
    assert version.core_values_tags == []
    assert version.deal_breakers_tags == []
    assert version.created_via == "wizard"


@pytest.mark.django_db
def test_version_number_unique_per_profile():
    profile = ValuesProfileModel.objects.create(id=_new_id(), user_id=1)
    ValuesProfileVersionModel.objects.create(id=_new_id(), profile=profile, version_number=1)
    with pytest.raises(IntegrityError):
        ValuesProfileVersionModel.objects.create(id=_new_id(), profile=profile, version_number=1)


@pytest.mark.django_db
def test_same_version_number_allowed_across_profiles():
    p1 = ValuesProfileModel.objects.create(id=_new_id(), user_id=1)
    p2 = ValuesProfileModel.objects.create(id=_new_id(), user_id=2)
    ValuesProfileVersionModel.objects.create(id=_new_id(), profile=p1, version_number=1)
    # Same version_number on a different profile is fine.
    ValuesProfileVersionModel.objects.create(id=_new_id(), profile=p2, version_number=1)


@pytest.mark.django_db
def test_current_version_pointer():
    profile = ValuesProfileModel.objects.create(id=_new_id(), user_id=1)
    v1 = ValuesProfileVersionModel.objects.create(id=_new_id(), profile=profile, version_number=1)
    profile.current_version = v1
    profile.save()

    profile.refresh_from_db()
    assert profile.current_version_id == v1.id


@pytest.mark.django_db
def test_versions_related_name():
    profile = ValuesProfileModel.objects.create(id=_new_id(), user_id=1)
    ValuesProfileVersionModel.objects.create(id=_new_id(), profile=profile, version_number=1)
    ValuesProfileVersionModel.objects.create(id=_new_id(), profile=profile, version_number=2)

    assert profile.versions.count() == 2
    numbers = sorted(profile.versions.values_list("version_number", flat=True))
    assert numbers == [1, 2]


@pytest.mark.django_db
def test_tag_creation_defaults():
    tag = ValuesTagModel.objects.create(
        id=_new_id(),
        field="core_values",
        slug="honesty",
        label="Honesty",
    )
    assert tag.status == "candidate"
    assert tag.usage_count == 0
    assert tag.promoted_at is None
    assert tag.created_at is not None


@pytest.mark.django_db
def test_tag_field_slug_unique():
    ValuesTagModel.objects.create(
        id=_new_id(), field="core_values", slug="honesty", label="Honesty"
    )
    with pytest.raises(IntegrityError):
        ValuesTagModel.objects.create(
            id=_new_id(), field="core_values", slug="honesty", label="Honesty (dupe)"
        )


@pytest.mark.django_db
def test_same_slug_allowed_across_fields():
    """Same slug in different fields is allowed (e.g. 'family' as core value and priority)."""
    ValuesTagModel.objects.create(id=_new_id(), field="core_values", slug="family", label="Family")
    # Same slug in a different field is fine.
    ValuesTagModel.objects.create(id=_new_id(), field="priorities", slug="family", label="Family")

    assert ValuesTagModel.objects.filter(slug="family").count() == 2


@pytest.mark.django_db
def test_tag_status_choices_persisted():
    tag = ValuesTagModel.objects.create(
        id=_new_id(),
        field="deal_breakers",
        slug="harm-children",
        label="No harm to children",
        status="seeded",
    )
    assert tag.status == "seeded"
    tag.status = "promoted"
    tag.save()
    tag.refresh_from_db()
    assert tag.status == "promoted"
