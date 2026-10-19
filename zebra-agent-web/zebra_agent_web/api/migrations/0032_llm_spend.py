"""LLM spend ledger: one row per LLM call; the daily budget sums it (#206)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0031_gym_scores"),
    ]

    operations = [
        migrations.CreateModel(
            name="LLMSpendModel",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("occurred_at", models.DateTimeField(db_index=True)),
                ("cost", models.DecimalField(decimal_places=8, default=0, max_digits=12)),
                ("input_tokens", models.IntegerField(default=0)),
                ("output_tokens", models.IntegerField(default=0)),
                ("model", models.CharField(blank=True, default="", max_length=255)),
                (
                    "process_id",
                    models.CharField(blank=True, db_index=True, max_length=255, null=True),
                ),
            ],
            options={
                "verbose_name": "LLM Spend",
                "verbose_name_plural": "LLM Spend",
                "db_table": "zebra_llm_spend",
            },
        ),
    ]
