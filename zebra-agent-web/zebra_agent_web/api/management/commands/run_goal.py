"""Django management command to submit a goal to Zebra and wait for completion.

Usage:
    python manage.py run_goal "Your goal text here"
    python manage.py run_goal "Your goal text" --model haiku

Used by scripts/zebra-feedback.sh to consult the production Zebra instance
from the local machine without requiring web authentication.
"""

import asyncio
import json
import logging
import uuid

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Submit a goal and wait for completion, printing the output as JSON."

    def add_arguments(self, parser):
        parser.add_argument("goal", type=str, help="The goal text to process")
        parser.add_argument(
            "--model",
            default="haiku",
            choices=["haiku", "sonnet", "opus", "kimi"],
            help="LLM model to use (default: haiku)",
        )

    def handle(self, *args, **options):
        goal = options["goal"]
        model = options["model"]

        try:
            result = asyncio.run(self._run(goal, model))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Goal failed: {e}"))
            logger.exception("run_goal management command failed")
            raise SystemExit(1)

        self.stdout.write(
            json.dumps(
                {
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                    "workflow_name": result.workflow_name,
                    "tokens_used": result.tokens_used,
                },
                indent=2,
            )
        )

    async def _run(self, goal: str, model: str):
        from zebra_agent_web.api import agent_engine

        await agent_engine.ensure_initialized()
        agent_loop = agent_engine.get_agent_loop()

        run_id = str(uuid.uuid4())

        # Derive provider from model alias so non-Anthropic models route correctly
        _MODEL_PROVIDERS = {"kimi": "kimi"}
        provider = _MODEL_PROVIDERS.get(model)

        original_provider = agent_loop.provider_name
        if provider:
            agent_loop.provider_name = provider

        try:
            return await agent_loop.process_goal(goal=goal, model=model, run_id=run_id)
        finally:
            agent_loop.provider_name = original_provider
