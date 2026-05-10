# Merge migration: reconciles F32 knowledge-lifecycle (0016_knowledgeentrymodel_deleted_at_and_more)
# with F20 ethics-audit-trail (0016_ethicsauditentrymodel), which were both branched from 0015.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0016_ethicsauditentrymodel"),
        ("api", "0016_knowledgeentrymodel_deleted_at_and_more"),
    ]

    operations = []
