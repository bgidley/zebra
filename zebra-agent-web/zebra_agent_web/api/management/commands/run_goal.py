"""Django management command to submit a goal to Zebra and wait for completion.

Usage:
    python manage.py run_goal "Your goal text here"
    python manage.py run_goal "Your goal text" --model haiku

Used by scripts/zebra-feedback.sh to consult the production Zebra instance
from the local machine without requiring web authentication.

Human tasks (e.g. ethics confirmation) are auto-approved so the command
does not block waiting for a web UI interaction.
"""

import asyncio
import json
import logging
import uuid

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

# Task definition IDs that are safe to auto-approve in automated contexts.
_AUTO_APPROVE_TASK_IDS = {"ethics_human_confirmation"}

# Field and value used when auto-approving a confirmation task.
_AUTO_APPROVE_OUTPUT = {"confirmed": True, "notes": "Auto-approved by run_goal command"}


class Command(BaseCommand):
    help = "Submit a goal and wait for completion, printing the output as JSON."

    def add_arguments(self, parser):
        parser.add_argument("goal", type=str, help="The goal text to process")
        parser.add_argument(
            "--model",
            default="haiku",
            choices=["haiku", "sonnet", "opus"],
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
        from zebra.core.models import ProcessState, TaskResult

        from zebra_agent_web.api import agent_engine
        from zebra_agent_web.api.engine import get_engine

        await agent_engine.ensure_initialized()
        agent_loop = agent_engine.get_agent_loop()
        engine = get_engine()

        run_id = str(uuid.uuid4())

        # Run process_goal in background; concurrently auto-approve any human tasks
        goal_task = asyncio.create_task(
            agent_loop.process_goal(goal=goal, model=model, run_id=run_id)
        )

        # Poll for READY human tasks belonging to our run and auto-complete them
        while not goal_task.done():
            await asyncio.sleep(2)
            try:
                processes = await engine.store.get_processes_by_state(ProcessState.RUNNING)
                for proc in processes:
                    if proc.properties.get("run_id") != run_id:
                        continue
                    pending = await engine.get_pending_tasks(proc.id)
                    for task in pending:
                        if task.task_definition_id in _AUTO_APPROVE_TASK_IDS:
                            logger.info(
                                "run_goal: auto-approving task %s (%s)",
                                task.id,
                                task.task_definition_id,
                            )
                            await engine.complete_task(
                                task.id, TaskResult.ok(output=_AUTO_APPROVE_OUTPUT)
                            )
            except Exception:
                pass  # don't let polling errors kill the main task

        return await goal_task
