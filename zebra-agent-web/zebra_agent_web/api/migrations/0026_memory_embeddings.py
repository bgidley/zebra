"""Add Oracle VECTOR embedding columns to the memory and knowledge tables (#169).

Oracle only: other backends keep keyword-ranked retrieval. The columns are not
declared on the Django models (see ``zebra_agent_web.embeddings``). The model,
triggers and backfill are set up by ``manage.py load_embedding_model``, which
the container entrypoint runs after ``migrate``.
"""

from django.db import migrations


def add_columns(apps, schema_editor):
    if schema_editor.connection.vendor != "oracle":
        return
    from zebra_agent_web.embeddings import ensure_vector_columns

    with schema_editor.connection.cursor() as cursor:
        ensure_vector_columns(cursor)


def drop_columns(apps, schema_editor):
    if schema_editor.connection.vendor != "oracle":
        return
    from zebra_agent_web.embeddings import drop_vector_columns

    with schema_editor.connection.cursor() as cursor:
        drop_vector_columns(cursor)


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0025_knowledge_world_category"),
    ]

    operations = [
        migrations.RunPython(add_columns, drop_columns),
    ]
