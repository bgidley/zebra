"""One postmortem per run on every backend, Oracle included (#175).

0028's conditional unique constraint is ignored on Oracle (models.W036). A run
with no id is now stored as NULL, so a plain unique constraint works everywhere.
"""

from django.db import migrations, models


def blank_run_ids_to_null(apps, schema_editor):
    PostmortemModel = apps.get_model("api", "PostmortemModel")
    PostmortemModel.objects.filter(run_id="").update(run_id=None)


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0028_postmortems"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="postmortemmodel",
            name="zebra_postmortem_one_per_run",
        ),
        migrations.AlterField(
            model_name="postmortemmodel",
            name="run_id",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.RunPython(blank_run_ids_to_null, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="postmortemmodel",
            name="run_id",
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
    ]
