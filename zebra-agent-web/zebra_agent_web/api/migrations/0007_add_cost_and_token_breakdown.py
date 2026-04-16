"""Add cost and input/output token breakdown to WorkflowRunModel."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0006_add_model_to_runs_and_memory"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowrunmodel",
            name="input_tokens",
            field=models.IntegerField(default=0, help_text="Input (prompt) tokens used"),
        ),
        migrations.AddField(
            model_name="workflowrunmodel",
            name="output_tokens",
            field=models.IntegerField(default=0, help_text="Output (completion) tokens used"),
        ),
        migrations.AddField(
            model_name="workflowrunmodel",
            name="cost",
            field=models.DecimalField(
                decimal_places=6,
                default=0,
                help_text="USD cost of this run",
                max_digits=10,
            ),
        ),
    ]
