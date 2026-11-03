"""Export one workflow as a signed Commons file (#229 S2b).

Usage:
    python manage.py commons_export "Web Research" --out web_research.zebra.json

Signed with this device's key and attributed to the Zebra by its ``DEVICE_CERT``.
Refused unless the workflow may leave the deployment (``commons_exportable``). Writes
the file (or stdout with ``--out -``); exits 1 with the reason on failure.
"""

import asyncio
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Export a workflow as a signed Commons file."

    def add_arguments(self, parser):
        parser.add_argument("name", help="Workflow name")
        parser.add_argument("--out", default="-", help="Output file, or - for stdout")

    def handle(self, *args, **options):
        from zebra_agent_web.api.commons_export import export_workflow_file

        try:
            text = asyncio.run(export_workflow_file(options["name"]))
        except ValueError as e:  # CommonsError, ExportRefused
            self.stderr.write(f"Export refused: {e}")
            raise SystemExit(1) from e
        if options["out"] == "-":
            self.stdout.write(text, ending="")
        else:
            Path(options["out"]).write_text(text)
            self.stderr.write(f"Wrote {options['out']}")
