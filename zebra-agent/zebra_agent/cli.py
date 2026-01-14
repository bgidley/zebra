"""Interactive console CLI for the Zebra Agent."""

import asyncio
import sys
from pathlib import Path

from zebra.core.engine import WorkflowEngine
from zebra.storage.sqlite import SQLiteStore
from zebra.tasks.registry import ActionRegistry

from zebra_tasks.llm.action import LLMCallAction

from zebra_agent.library import WorkflowLibrary
from zebra_agent.loop import AgentLoop
from zebra_agent.metrics import MetricsStore


# Default paths
DEFAULT_DATA_DIR = Path("~/.zebra-agent").expanduser()
DEFAULT_WORKFLOWS_DIR = DEFAULT_DATA_DIR / "workflows"
DEFAULT_STATE_DB = DEFAULT_DATA_DIR / "state.db"
DEFAULT_METRICS_DB = DEFAULT_DATA_DIR / "metrics.db"

# Built-in workflows location (relative to package)
BUILTIN_WORKFLOWS = Path(__file__).parent.parent / "workflows"


def print_banner():
    """Print the welcome banner."""
    print(
        """
╔═══════════════════════════════════════════════════════════╗
║                     Zebra Agent                           ║
║         Self-improving workflow assistant                 ║
╠═══════════════════════════════════════════════════════════╣
║  Commands:                                                ║
║    /list     - Show available workflows                   ║
║    /stats    - Show workflow statistics                   ║
║    /help     - Show this help                             ║
║    /quit     - Exit the agent                             ║
║                                                           ║
║  Or just type your goal and press Enter!                  ║
╚═══════════════════════════════════════════════════════════╝
"""
    )


async def cmd_list(library: WorkflowLibrary):
    """List available workflows."""
    workflows = await library.list_workflows()

    if not workflows:
        print("\n  No workflows available yet. Try entering a goal to create one!\n")
        return

    print("\n  Available Workflows:")
    print("  " + "─" * 60)

    for w in workflows:
        tags = ", ".join(w.tags[:3]) if w.tags else "none"
        success = f"{w.success_rate:.0%}" if w.use_count > 0 else "N/A"
        print(f"  • {w.name}")
        print(f"    {w.description}")
        print(f"    Tags: {tags} | Success: {success} | Uses: {w.use_count}")
        print()


async def cmd_stats(metrics: MetricsStore):
    """Show workflow statistics."""
    all_stats = await metrics.get_all_stats()
    recent_runs = await metrics.get_recent_runs(5)

    print("\n  Workflow Statistics:")
    print("  " + "─" * 60)

    if all_stats:
        print("\n  By Workflow:")
        for s in all_stats:
            success = f"{s.success_rate:.0%}"
            rating = f"{s.avg_rating:.1f}/5" if s.avg_rating else "N/A"
            print(f"  • {s.workflow_name}")
            print(f"    Runs: {s.total_runs} | Success: {success} | Avg Rating: {rating}")
    else:
        print("\n  No workflow runs recorded yet.")

    if recent_runs:
        print("\n  Recent Runs:")
        for r in recent_runs:
            status = "✓" if r.success else "✗"
            rating = f"({r.user_rating}/5)" if r.user_rating else ""
            goal_preview = r.goal[:40] + "..." if len(r.goal) > 40 else r.goal
            print(f"  {status} {r.workflow_name}: {goal_preview} {rating}")

    print()


def cmd_help():
    """Show help message."""
    print(
        """
  Commands:
    /list     - Show all available workflows with descriptions
    /stats    - Show usage statistics and recent runs
    /help     - Show this help message
    /quit     - Exit the agent (also: /exit, /q)

  Usage:
    Simply type your goal or question and press Enter.
    The agent will select the best workflow or create a new one.

  After each response, you can rate the result (1-5) to help
  improve workflow selection over time.

  Examples:
    > What is the capital of France?
    > Brainstorm ideas for a birthday party
    > Summarize the key points of this article: ...
    > Help me analyze this problem: ...
"""
    )


async def async_main():
    """Main async entry point."""
    # Ensure data directory exists
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize components
    metrics = MetricsStore(DEFAULT_METRICS_DB)
    library = WorkflowLibrary(DEFAULT_WORKFLOWS_DIR, metrics)

    # Copy built-in workflows if library is empty
    if BUILTIN_WORKFLOWS.exists():
        copied = library.copy_builtin_workflows(BUILTIN_WORKFLOWS)
        if copied > 0:
            print(f"  Copied {copied} built-in workflows to library.")

    # Initialize workflow engine
    store = SQLiteStore(str(DEFAULT_STATE_DB))
    await store.initialize()

    # Register LLM action
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("llm_call", LLMCallAction)

    engine = WorkflowEngine(store, registry)

    # Create agent loop
    agent = AgentLoop(
        library=library,
        engine=engine,
        metrics=metrics,
        provider="anthropic",
    )

    print_banner()

    while True:
        try:
            # Get input
            goal = input("\n> ").strip()

            if not goal:
                continue

            # Handle commands
            if goal.startswith("/"):
                cmd = goal.lower()

                if cmd in ("/quit", "/exit", "/q"):
                    print("\n  Goodbye!\n")
                    break
                elif cmd == "/list":
                    await cmd_list(library)
                elif cmd == "/stats":
                    await cmd_stats(metrics)
                elif cmd == "/help":
                    cmd_help()
                else:
                    print(f"\n  Unknown command: {goal}")
                    print("  Type /help for available commands.\n")
                continue

            # Process goal
            print("\n  Processing...\n")

            result = await agent.process_goal(goal)

            if result.success:
                # Show workflow used
                if result.created_new_workflow:
                    print(f"  [Created new workflow: {result.workflow_name}]\n")
                else:
                    print(f"  [Using workflow: {result.workflow_name}]\n")

                # Show output
                if isinstance(result.output, dict):
                    for key, value in result.output.items():
                        print(f"  {value}\n")
                else:
                    print(f"  {result.output}\n")

                # Show token usage
                if result.tokens_used > 0:
                    print(f"  [Tokens used: {result.tokens_used}]")

                # Ask for rating
                try:
                    rating_input = input("\n  Rate this result (1-5, or Enter to skip): ").strip()
                    if rating_input and rating_input.isdigit():
                        rating = int(rating_input)
                        if 1 <= rating <= 5:
                            await agent.record_rating(result.run_id, rating)
                            print("  Thanks for the feedback!")
                        else:
                            print("  Rating must be between 1 and 5.")
                except (EOFError, KeyboardInterrupt):
                    pass
            else:
                print(f"  Error: {result.error}\n")

        except KeyboardInterrupt:
            print("\n\n  Use /quit to exit.\n")
        except EOFError:
            print("\n  Goodbye!\n")
            break
        except Exception as e:
            print(f"\n  Error: {e}\n")


def run():
    """Entry point for the CLI."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n  Goodbye!\n")
        sys.exit(0)


if __name__ == "__main__":
    run()
