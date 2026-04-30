"""Seed the ValuesTagModel with the LLM-bootstrapped starter taxonomy.

Loads ``zebra-agent-web/fixtures/values_taxonomy_seed.yaml`` (produced by
``manage.py bootstrap_values_taxonomy`` and hand-reviewed) into ``Tag`` rows
with ``status="seeded"``. The reverse migration removes only the rows this
migration inserted (matched by ``(field, slug)`` against the fixture); any
candidate or promoted tags accumulated since are left intact.

Idempotent: ``get_or_create`` skips rows that already exist (e.g. if the
fixture is reloaded after a partial run or in a staging env).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import yaml
from django.db import migrations

# fixture lives at: zebra-agent-web/fixtures/values_taxonomy_seed.yaml
# this file is at:  zebra-agent-web/zebra_agent_web/api/migrations/0013_*.py
# walk up: migrations -> api -> zebra_agent_web -> zebra-agent-web
_FIXTURE_PATH = Path(__file__).resolve().parents[3] / "fixtures" / "values_taxonomy_seed.yaml"


def _load_fixture() -> dict:
    if not _FIXTURE_PATH.exists():
        # Allow migrate to succeed in environments without the fixture
        # (e.g. fresh checkouts before bootstrap has been run). The taxonomy
        # will simply start empty; users can still capture profiles, the LLM
        # will just propose more candidate tags.
        return {}
    return yaml.safe_load(_FIXTURE_PATH.read_text()) or {}


def seed_taxonomy(apps, schema_editor):
    Tag = apps.get_model("api", "ValuesTagModel")
    data = _load_fixture()
    for field, entries in data.items():
        for entry in entries or []:
            slug = (entry.get("slug") or "").strip()
            if not slug:
                continue
            Tag.objects.get_or_create(
                field=field,
                slug=slug,
                defaults={
                    "id": str(uuid.uuid4()),
                    "label": entry.get("label") or slug,
                    "description": entry.get("description") or "",
                    "status": "seeded",
                    "usage_count": 0,
                },
            )


def unseed_taxonomy(apps, schema_editor):
    Tag = apps.get_model("api", "ValuesTagModel")
    data = _load_fixture()
    for field, entries in data.items():
        for entry in entries or []:
            slug = (entry.get("slug") or "").strip()
            if not slug:
                continue
            Tag.objects.filter(field=field, slug=slug, status="seeded").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0012_valuesprofilemodel_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_taxonomy, reverse_code=unseed_taxonomy),
    ]
