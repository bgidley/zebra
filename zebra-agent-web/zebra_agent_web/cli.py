"""CLI entry points for zebra-agent-web.

Provides commands to run the development and production servers:
- zebra-web-agent: Production server on localhost:8000
- zebra-web-agent-public: Production server on 0.0.0.0:8000
- zebra-web-agent-dev: Development server on localhost:8000
- zebra-web-agent-dev-public: Development server on 0.0.0.0:8000

And the ``zebra`` terminal client (F34 / REQ-UI-003), which shares the same
Oracle-backed stores as the web app:
- zebra goal "<text>" [--model ...] [--queue] [--priority N]
- zebra goals [--limit N]
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _load_env():
    """Load environment variables from .env file."""
    # Try to find .env in current directory or parent directories
    current = Path.cwd()
    for path in [current, current.parent, current.parent.parent]:
        env_file = path / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            break


def _setup_django():
    """Set up Django settings module."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zebra_agent_web.settings")


def serve():
    """Run the production ASGI server with Daphne on localhost:8000."""
    _load_env()
    _setup_django()
    from daphne.cli import CommandLineInterface

    sys.argv = ["daphne", "-b", "127.0.0.1", "-p", "8000", "zebra_agent_web.asgi:application"]
    CommandLineInterface().run(sys.argv[1:])


def serve_public():
    """Run the production ASGI server with Daphne on 0.0.0.0:8000."""
    _load_env()
    _setup_django()
    from daphne.cli import CommandLineInterface

    sys.argv = ["daphne", "-b", "0.0.0.0", "-p", "8000", "zebra_agent_web.asgi:application"]
    CommandLineInterface().run(sys.argv[1:])


def dev():
    """Run the Django development server on localhost:8000."""
    _load_env()
    _setup_django()
    from django.core.management import execute_from_command_line

    sys.argv = ["manage.py", "runserver", "127.0.0.1:8000"]
    execute_from_command_line(sys.argv)


def dev_public():
    """Run the Django development server on 0.0.0.0:8000."""
    _load_env()
    _setup_django()
    from django.core.management import execute_from_command_line

    sys.argv = ["manage.py", "runserver", "0.0.0.0:8000"]
    execute_from_command_line(sys.argv)


# ---------------------------------------------------------------------------
# zebra terminal client (F34 / REQ-UI-003)
# ---------------------------------------------------------------------------

# Model aliases that require a non-default LLM provider.
_MODEL_PROVIDERS = {"kimi": "kimi"}


def _init_django() -> None:
    """Load .env and initialise Django for standalone (non-server) use."""
    _load_env()
    _setup_django()
    import django

    django.setup()


def _check_backend(allow_sqlite: bool) -> None:
    """Abort unless the active DB backend is Oracle (or --allow-sqlite given).

    Django settings silently fall back to SQLite when ORACLE_* variables are
    missing; without this guard the CLI would "succeed" against a local
    db.sqlite3 that the web dashboard never reads.
    """
    from django.db import connections

    vendor = connections["default"].vendor
    if vendor == "oracle" or allow_sqlite:
        return
    print(
        f"Error: active database backend is '{vendor}', not Oracle.\n"
        "The web dashboard reads Oracle — goals written here would not appear in it.\n"
        "Set ORACLE_DSN, ORACLE_USERNAME and ORACLE_PASSWORD (e.g. in .env),\n"
        "or pass --allow-sqlite to run against the local SQLite database anyway.",
        file=sys.stderr,
    )
    sys.exit(1)


async def _goal_async(text: str, model: str, queue: bool, priority: int) -> int:
    """Run or queue a goal. Returns the process exit code."""
    from zebra_agent_web.api import agent_engine

    if queue:
        from zebra_agent_web.api.goals import queue_goal

        process = await queue_goal(text, model=model, priority=priority)
        print(f"Goal queued as process {process.id}")
        print("The budget daemon will start it when budget allows.")
        return 0

    await agent_engine.ensure_initialized()
    agent_loop = agent_engine.get_agent_loop()

    # Route non-Anthropic model aliases to their provider (mirrors run_goal).
    original_provider = agent_loop.provider_name
    provider = _MODEL_PROVIDERS.get(model)
    if provider:
        agent_loop.provider_name = provider

    async def progress(event: str, data: dict) -> None:
        label = data.get("task_name") or data.get("workflow_name") or ""
        print(f"  [{event}] {label}".rstrip())

    import uuid

    run_id = str(uuid.uuid4())

    try:
        result = await agent_loop.process_goal(
            goal=text, model=model, run_id=run_id, progress_callback=progress
        )
    finally:
        agent_loop.provider_name = original_provider

    print()
    print(f"Run ID:   {result.run_id}")
    print(f"Workflow: {result.workflow_name}")
    print(f"Success:  {result.success}")
    if result.tokens_used:
        print(f"Tokens:   {result.tokens_used}")
    if result.error:
        print(f"Error:    {result.error}")
    print()
    if result.output is not None:
        print(result.output)
    return 0 if result.success else 1


async def _goals_async(limit: int) -> int:
    """List recent workflow runs from the shared store."""
    from zebra_agent_web.metrics_store import DjangoMetricsStore

    store = DjangoMetricsStore()
    await store.initialize()
    runs = await store.get_recent_runs(limit=limit)
    if not runs:
        print("No runs recorded yet.")
        return 0

    print(f"{'run id':<10} {'when':<17} {'ok':<3} {'workflow':<28} goal")
    for run in runs:
        started = run.started_at.strftime("%Y-%m-%d %H:%M") if run.started_at else "-"
        ok = "Y" if run.success else "N"
        goal = (run.goal or "")[:50]
        print(f"{run.id[:8]:<10} {started:<17} {ok:<3} {(run.workflow_name or '')[:28]:<28} {goal}")
    return 0


def main() -> None:
    """Entry point for the ``zebra`` terminal client."""
    parser = argparse.ArgumentParser(
        prog="zebra",
        description=(
            "Zebra terminal client — shares Oracle storage with the web app, "
            "so goals submitted here appear in the dashboard. "
            "First call takes a couple of seconds to initialise Django."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    goal_p = sub.add_parser("goal", help="Process (or queue) a goal")
    goal_p.add_argument("text", help="The goal text")
    goal_p.add_argument(
        "--model",
        default="haiku",
        choices=["haiku", "sonnet", "opus", "kimi"],
        help="LLM model to use (default: haiku)",
    )
    goal_p.add_argument(
        "--queue",
        action="store_true",
        help="Queue for daemon execution instead of running now",
    )
    goal_p.add_argument(
        "--priority",
        type=int,
        default=3,
        help="Queue priority 1 (highest) to 5 (default: 3; queue mode only)",
    )
    goal_p.add_argument(
        "--allow-sqlite",
        action="store_true",
        help="Permit running against the SQLite fallback database",
    )

    goals_p = sub.add_parser("goals", help="List recent goal runs")
    goals_p.add_argument("--limit", type=int, default=10, help="Max runs to list (default: 10)")
    goals_p.add_argument(
        "--allow-sqlite",
        action="store_true",
        help="Permit running against the SQLite fallback database",
    )

    args = parser.parse_args()

    _init_django()
    _check_backend(args.allow_sqlite)

    if args.command == "goal":
        exit_code = asyncio.run(_goal_async(args.text, args.model, args.queue, args.priority))
    else:
        exit_code = asyncio.run(_goals_async(args.limit))
    sys.exit(exit_code)


if __name__ == "__main__":
    dev()
