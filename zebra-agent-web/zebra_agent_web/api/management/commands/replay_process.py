"""Django management command to replay a finished process from its recording (#170).

Usage:
    python manage.py replay_process <process_id>
    python manage.py replay_process <process_id> --live work --continue-live
    python manage.py replay_process <process_id> --definition fixed.yaml

Each step is served from what the original recorded, so an unchanged replay
costs nothing and ends the way the original did. ``--live`` steps (and steps a
``--definition`` changes) run for real, with their cost and side effects.
Prints ``{status, process_id, replay_of, live, cost, output, error, ...}`` as
JSON. Exits 1 when the replay could not start.
"""

import asyncio
import json
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Replay a finished process from its step journal, optionally running steps live."

    def add_arguments(self, parser):
        parser.add_argument("process_id", help="COMPLETE or FAILED process to replay")
        parser.add_argument(
            "--live",
            action="append",
            default=[],
            metavar="STEP",
            help="Step (task definition) id to run live; repeatable",
        )
        parser.add_argument(
            "--definition",
            default=None,
            help="YAML/JSON workflow file to replay against; its changed steps run live",
        )
        parser.add_argument(
            "--continue-live",
            action="store_true",
            help="Run steps the original never reached live instead of failing at them",
        )
        parser.add_argument(
            "--timeout", type=float, default=900.0, help="Seconds the auto steps may run"
        )

    def handle(self, *args, **options):
        live = options["live"]
        if live or options["definition"] or options["continue_live"]:
            self.stderr.write(
                "Warning: live steps run for real, with their LLM cost and side effects."
            )
        try:
            result = asyncio.run(self._run(options))
        except Exception as e:
            logger.exception("replay_process failed")
            result = {"status": "error", "error": str(e)}

        self.stdout.write(json.dumps(result, indent=2, default=str))
        if result.get("status") == "error":
            raise SystemExit(1)

    async def _run(self, options) -> dict:
        from zebra.definitions.loader import load_definition
        from zebra_agent.replay import replay_process

        from zebra_agent_web.api import agent_engine

        await agent_engine.ensure_initialized()
        engine = agent_engine.get_agent_loop().engine
        definition = load_definition(options["definition"]) if options["definition"] else None
        return await replay_process(
            engine,
            options["process_id"],
            live=options["live"],
            definition=definition,
            continue_live=options["continue_live"],
            timeout=options["timeout"],
        )
