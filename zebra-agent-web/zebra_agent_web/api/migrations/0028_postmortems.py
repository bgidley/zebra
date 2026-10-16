"""Postmortem journal table (#175), with its Oracle VECTOR embedding column.

The embedding column, like those added in 0026, is not declared on the model;
``manage.py load_embedding_model`` installs its trigger and backfills it.
"""

from django.db import migrations, models


def add_columns(apps, schema_editor):
    if schema_editor.connection.vendor != "oracle":
        return
    from zebra_agent_web.embeddings import ensure_vector_columns

    with schema_editor.connection.cursor() as cursor:
        ensure_vector_columns(cursor)


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0027_process_events"),
    ]

    operations = [
        migrations.CreateModel(
            name="PostmortemModel",
            fields=[
                ("id", models.CharField(max_length=255, primary_key=True, serialize=False)),
                ("user_id", models.IntegerField(blank=True, db_index=True, null=True)),
                ("timestamp", models.DateTimeField(db_index=True)),
                (
                    "run_id",
                    models.CharField(blank=True, db_index=True, default="", max_length=255),
                ),
                ("goal", models.TextField()),
                ("workflow_name", models.CharField(blank=True, default="", max_length=255)),
                (
                    "trigger",
                    models.CharField(help_text="failure | timeout | low_rating", max_length=20),
                ),
                ("what_happened", models.TextField(blank=True, default="")),
                ("root_cause", models.TextField(blank=True, default="")),
                ("lesson", models.TextField()),
                ("voice", models.TextField(blank=True, null=True)),
                ("confidence", models.FloatField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Postmortem",
                "verbose_name_plural": "Postmortems",
                "db_table": "zebra_postmortems",
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("run_id", ""), _negated=True),
                        fields=("run_id",),
                        name="zebra_postmortem_one_per_run",
                    )
                ],
                "indexes": [
                    models.Index(fields=["-timestamp"], name="zebra_postm_timesta_1d3dd2_idx")
                ],
            },
        ),
        migrations.RunPython(add_columns, migrations.RunPython.noop),
    ]
