"""Django management command to run a named workflow directly, or report its status.

Usage:
    python manage.py run_workflow "Outcome Review" --input-file - < inputs.json
    python manage.py run_workflow --status <process_id>

Prints ``{status, process_id, run_id, task_id, output, error}`` as JSON, where
status is complete / awaiting_input / failed / running. Exits 1 when the run
failed or could not start. Used by scripts/zebra-outcome-review.sh inside the
prod ``zebra-web`` container (#190).
"""

import asyncio
import json
import logging
import sys

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run a named workflow with JSON inputs (no workflow selection), or report status."

    def add_arguments(self, parser):
        parser.add_argument("workflow", nargs="?", help="Workflow name to run")
        parser.add_argument(
            "--input-file",
            default=None,
            help="JSON object of inputs; '-' reads stdin",
        )
        parser.add_argument("--status", default=None, help="Report on this process id instead")
        parser.add_argument(
            "--model",
            default="sonnet",
            choices=["haiku", "sonnet", "opus", "kimi", "openrouter"],
            help="LLM model for the run (default: sonnet)",
        )
        parser.add_argument(
            "--timeout", type=float, default=900.0, help="Seconds the auto tasks may run"
        )

    def handle(self, *args, **options):
        try:
            result = asyncio.run(self._run(options))
        except Exception as e:
            logger.exception("run_workflow failed")
            result = {"status": "failed", "error": str(e)}

        self.stdout.write(json.dumps(result, indent=2, default=str))
        if result.get("status") == "failed":
            raise SystemExit(1)

    async def _run(self, options) -> dict:
        from zebra_agent.direct_run import DirectRunError, run_named_workflow, workflow_status

        from zebra_agent_web.api import agent_engine

        await agent_engine.ensure_initialized()
        engine = agent_engine.get_agent_loop().engine

        if options["status"]:
            return await workflow_status(engine, options["status"])

        if not options["workflow"]:
            return {"status": "failed", "error": "Give a workflow name or --status"}

        inputs: dict = {}
        if options["input_file"]:
            if options["input_file"] == "-":
                raw = sys.stdin.read()
            else:
                with open(options["input_file"]) as f:
                    raw = f.read()
            inputs = json.loads(raw) if raw.strip() else {}
            if not isinstance(inputs, dict):
                return {"status": "failed", "error": "Inputs must be a JSON object"}

        model = options["model"]
        provider = {"kimi": "kimi", "openrouter": "openrouter"}.get(
            model, agent_engine.get_llm_provider_name()
        )
        try:
            return await run_named_workflow(
                engine,
                agent_engine.get_library(),
                options["workflow"],
                inputs,
                provider=provider,
                model=model,
                timeout=options["timeout"],
            )
        except DirectRunError as e:
            return {"status": "failed", "error": str(e)}
