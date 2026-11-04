"""Verify (and optionally adopt) a signed Commons workflow file (#229 S2b).

Usage:
    python manage.py commons_import web_research.zebra.json
    python manage.py commons_import web_research.zebra.json --expect-zebra npub1... --adopt
    python manage.py commons_import web_research.zebra.json --judge

Verification checks the signature, the device's cert chain to its Zebra (and any
revoke this deployment holds), the content hash and that the workflow never saw other
users' runs. ``--adopt`` adds it to the library with its provenance kept and
``supervised: true``, as ``<name> (from <fingerprint>)`` unless ``--name`` is given:
running this command is the owner's approval. Prints JSON; exits 1 unless verified
(and adopted, with ``--adopt``).

``--judge`` (#230) runs the *Commons Import* workflow instead: personal-data scan,
ethics gate, golden-task gym and the ``sharing`` trust gate, then the owner's approval
task in the web UI (``/tasks/``). Prints the run's status; exits 1 if it was rejected.
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
        parser.add_argument(
            "--judge", action="store_true", help="Run the judged import pipeline (#230)"
        )

    def handle(self, *args, **options):
        from zebra_agent_web.api.commons_export import import_workflow_file

        text = Path(options["file"]).read_bytes().decode("utf-8", errors="replace")
        if options["judge"]:
            self._judge(text, options["expect_zebra"])
            return
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

    def _judge(self, text: str, expected: str | None) -> None:
        from zebra_agent.direct_run import workflow_status

        from zebra_agent_web.api import engine as engine_module
        from zebra_agent_web.api.commons_export import _pubkey
        from zebra_agent_web.api.commons_import import start_judged_import
        from zebra_agent_web.api.commons_owner import resolve_commons_owner

        async def run() -> dict:
            owner, *_ = await resolve_commons_owner()
            process_id = await start_judged_import(
                text, user_id=owner, expected_zebra=_pubkey(expected), wait=True
            )
            status = await workflow_status(engine_module.get_engine(), process_id)
            process = await engine_module.get_store().load_process(process_id)
            status["result"] = (process.properties or {}).get("commons_import_result")
            return status

        try:
            status = asyncio.run(run())
        except ValueError as e:  # CommonsError
            status = {"status": "failed", "error": str(e)}
        self.stdout.write(json.dumps(status, indent=2, default=str))
        result = status.get("result") or {}
        if status["status"] == "failed" or result.get("status") == "rejected":
            raise SystemExit(1)
