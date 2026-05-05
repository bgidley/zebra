"""Add RoutineRunModel table for the polling scheduler (F27 / REQ-PRIN-008)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0013_seed_values_taxonomy"),
    ]

    operations = [
        migrations.CreateModel(
            name="RoutineRunModel",
            fields=[
                (
                    "routine_name",
                    models.CharField(max_length=255, primary_key=True, serialize=False),
                ),
                ("last_run", models.DateTimeField(blank=True, null=True)),
                ("next_run", models.DateTimeField()),
                ("last_status", models.CharField(default="pending", max_length=50)),
            ],
            options={
                "verbose_name": "Routine Run",
                "verbose_name_plural": "Routine Runs",
                "db_table": "zebra_routine_runs",
            },
        ),
    ]
