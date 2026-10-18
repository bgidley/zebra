"""Journal the route each task chose, so a replay can follow it (#170)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0029_postmortem_unique_run"),
    ]

    operations = [
        migrations.AddField(
            model_name="processeventmodel",
            name="next_route",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
