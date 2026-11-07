"""Offer one library workflow to the public Zebra Commons (#231, S4).

Usage:
    python manage.py commons_offer "Web Research"

Runs the *Commons Offer* workflow as the Commons owner: preconditions (exportable, leak-free,
at least 5 runs), personal-data scan, ethics review, then the ``sharing`` trust gate or the
owner's approval task in the web UI (``/tasks/``), then publishing a signed ``OFFER``. Needs
``ZEBRA_COMMONS_ENABLED`` and ``ZEBRA_COMMONS_RELAYS``; without them the offer is refused with
that reason. Prints the run's status as JSON; exits 1 if it was refused or failed.
"""

import asyncio
import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Offer a workflow to the public Zebra Commons (needs ZEBRA_COMMONS_RELAYS)."

    def add_arguments(self, parser):
        parser.add_argument("name", help="Workflow name")

    def handle(self, *args, **options):
        from zebra_agent.direct_run import workflow_status

        from zebra_agent_web.api import engine as engine_module
        from zebra_agent_web.api.commons_owner import resolve_commons_owner
        from zebra_agent_web.api.commons_publish import start_offer

        async def run() -> dict:
            owner, *_ = await resolve_commons_owner()
            process_id = await start_offer(options["name"], user_id=owner)
            status = await workflow_status(engine_module.get_engine(), process_id)
            process = await engine_module.get_store().load_process(process_id)
            status["result"] = (process.properties or {}).get("commons_offer_result")
            return status

        status = asyncio.run(run())
        self.stdout.write(json.dumps(status, indent=2, default=str))
        result = status.get("result") or {}
        if status["status"] == "failed" or result.get("status") in ("refused", "declined"):
            raise SystemExit(1)
