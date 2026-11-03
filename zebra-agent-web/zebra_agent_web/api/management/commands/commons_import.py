"""Verify (and optionally adopt) a signed Commons workflow file (#229 S2b).

Usage:
    python manage.py commons_import web_research.zebra.json
    python manage.py commons_import web_research.zebra.json --expect-zebra npub1... --adopt

Verification checks the signature, the device's cert chain to its Zebra (and any
revoke this deployment holds), the content hash and that the workflow never saw other
users' runs. ``--adopt`` adds it to the library with its provenance kept and
``supervised: true``, as ``<name> (from <fingerprint>)`` unless ``--name`` is given:
running this command is the owner's approval. Prints JSON; exits 1 unless verified
(and adopted, with ``--adopt``).
"""

import asyncio
import json
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Verify a signed Commons workflow file; --adopt adds it to the library."

    def add_arguments(self, parser):
        parser.add_argument("file", help="Export file")
        parser.add_argument("--expect-zebra", default=None, help="Publisher npub or hex pubkey")
        parser.add_argument("--adopt", action="store_true", help="Adopt it once verified")
        parser.add_argument("--name", default=None, help="Local name for the adopted workflow")

    def handle(self, *args, **options):
        from zebra_agent_web.api.commons_export import import_workflow_file

        text = Path(options["file"]).read_bytes().decode("utf-8", errors="replace")
        try:
            result = asyncio.run(
                import_workflow_file(
                    text,
                    expected_zebra=options["expect_zebra"],
                    adopt=options["adopt"],
                    name=options["name"],
                )
            )
        except ValueError as e:  # CommonsError, AdoptionRefused
            result = {"ok": False, "reason": str(e), "adopted": False}
        self.stdout.write(json.dumps(result, indent=2))
        if not result["ok"] or (options["adopt"] and not result["adopted"]):
            raise SystemExit(1)
