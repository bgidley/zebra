"""Interactive console CLI for the Zebra Agent."""

import asyncio
import os
import sys
from pathlib import Path

from zebra.core.engine import WorkflowEngine
from zebra.storage.postgres import PostgreSQLStore
from zebra.tasks.registry import ActionRegistry
from zebra_agent.library import WorkflowLibrary
from zebra_agent.loop import AgentLoop
from zebra_agent.memory import AgentMemory
from zebra_agent.metrics import MetricsStore
from zebra_tasks.agent import (
    MetricsAnalyzerAction,
    WorkflowEvaluatorAction,
    WorkflowOptimizerAction,
)
from zebra_tasks.compute import PythonExecAction
from zebra_tasks.llm.action import LLMCallAction

# Default paths
DEFAULT_DATA_DIR = Path("~/.zebra-agent").expanduser()
DEFAULT_WORKFLOWS_DIR = DEFAULT_DATA_DIR / "workflows"

# Built-in workflows location (relative to package)
BUILTIN_WORKFLOWS = Path(__file__).parent.parent / "workflows"


def get_pg_config():
    """Get PostgreSQL configuration from environment variables."""
    return {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": int(os.environ.get("PGPORT", "5432")),
        "database": os.environ.get("PGDATABASE", "opc"),
        "user": os.environ.get("PGUSER", "opc"),
        "password": os.environ.get("PGPASSWORD"),
    }


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
║    /memory   - Show memory status                         ║
║    /dream    - Run self-improvement cycle                 ║
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
    /memory   - Show memory status and usage
    /dream    - Run self-improvement cycle (analyze & optimize workflows)
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


async def cmd_memory(memory: AgentMemory):
    """Show memory status."""
    print("\n  Memory Status:")
    print("  " + "─" * 60)

    stats = await memory.get_stats()
    short = stats["short_term"]
    long = stats["long_term"]

    # Short-term memory status
    short_total = short["entry_tokens"]
    short_threshold = int(memory.short_term_max_tokens * memory.compact_threshold)
    short_pct = (short_total / memory.short_term_max_tokens) * 100

    print("\n  SHORT-TERM MEMORY (details & recent context)")
    print(f"    Entries: {short['entry_count']} ({short_total:,} tokens)")
    print(f"    Summaries: {short['summary_count']} ({short['summary_tokens']:,} tokens)")
    print(f"    Limit: {memory.short_term_max_tokens:,} tokens (compact at {short_threshold:,})")
    print(f"    Usage: {short_pct:.1f}%")

    # Long-term memory status
    long_total = long["theme_tokens"] + short["summary_tokens"]
    long_threshold = int(memory.long_term_max_tokens * memory.compact_threshold)
    long_pct = (long_total / memory.long_term_max_tokens) * 100

    print("\n  LONG-TERM MEMORY (themes & patterns)")
    print(f"    Themes: {long['theme_count']} ({long['theme_tokens']:,} tokens)")
    print(f"    Limit: {memory.long_term_max_tokens:,} tokens (compact at {long_threshold:,})")
    print(f"    Usage: {long_pct:.1f}%")

    # Show recent entries
    entries = await memory.get_short_term_entries(limit=5)
    if entries:
        print("\n  Recent interactions (short-term):")
        for entry in entries:
            time_str = entry.timestamp.strftime("%Y-%m-%d %H:%M")
            goal_preview = entry.goal[:40] + "..." if len(entry.goal) > 40 else entry.goal
            print(f"    [{time_str}] {goal_preview}")
            print(f"      -> {entry.workflow_used} ({entry.tokens} tokens)")

    # Show recent summaries
    summaries = await memory.get_short_term_summaries(limit=2)
    if summaries:
        print("\n  Recent summaries (short-term):")
        for s in summaries:
            preview = s.summary[:150] + "..." if len(s.summary) > 150 else s.summary
            print(f"    [{s.created_at.strftime('%Y-%m-%d')}] {s.entry_count} entries summarized")
            print(f"      {preview}")

    # Show themes
    themes = await memory.get_long_term_themes(limit=2)
    if themes:
        print("\n  Themes (long-term):")
        for t in themes:
            preview = t.theme[:150] + "..." if len(t.theme) > 150 else t.theme
            date_str = t.created_at.strftime("%Y-%m-%d")
            refs_count = len(t.short_term_refs)
            print(f"    [{date_str}] refs: {refs_count} summaries")
            print(f"      {preview}")

    if not entries and not summaries and not themes:
        print("\n  No memory entries yet.")

    print()


async def cmd_dream(
    library: WorkflowLibrary,
    engine: WorkflowEngine,
    metrics: MetricsStore,
    provider: str = "anthropic",
):
    """Run the self-improvement dream cycle."""
    from zebra.core.models import ProcessState

    print("\n  Starting Dream Cycle...")
    print("  " + "─" * 60)
    print("  This will analyze performance and optimize workflows.")
    print()

    try:
        # Load the dream cycle workflow
        definition = library.get_workflow("Dream Cycle")
    except ValueError:
        print("  Error: Dream Cycle workflow not found.")
        print("  Make sure the built-in workflows have been copied to your library.")
        print()
        return

    # Create process with necessary properties
    process = await engine.create_process(
        definition,
        properties={
            "__llm_provider_name__": provider,
            "__workflow_library_path__": str(library.library_path),
        },
    )

    # Start and run
    await engine.start_process(process.id)

    print("  Running analysis...")

    # Wait for completion with progress updates
    import asyncio

    max_wait = 300  # 5 minutes max for dream cycle
    waited = 0
    last_task = ""

    while waited < max_wait:
        process = await engine.store.load_process(process.id)

        # Show current task
        current_task = process.properties.get("__current_task__", "")
        if current_task and current_task != last_task:
            print(f"    → {current_task}")
            last_task = current_task

        if process.state == ProcessState.COMPLETE:
            break
        elif process.state == ProcessState.FAILED:
            print(f"\n  Dream cycle failed: {process.error}")
            print()
            return

        await asyncio.sleep(1)
        waited += 1

    if process.state != ProcessState.COMPLETE:
        print("\n  Dream cycle timed out.")
        print()
        return

    # Show results
    print("\n  Dream Cycle Complete!")
    print("  " + "─" * 60)

    # Show summary if available
    summary = process.properties.get("dream_summary")
    if summary:
        print(f"\n  {summary}\n")

    # Show changes made
    results = process.properties.get("optimization_results", {})
    changes = results.get("changes_made", [])
    if changes:
        print("  Changes made:")
        for change in changes:
            print(f"    • {change.get('type', 'change')}: {change.get('workflow', 'unknown')}")
    else:
        print("  No changes were needed at this time.")

    print()


async def async_main():
    """Main async entry point."""
    # Ensure data directory exists
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    pg_config = get_pg_config()

    # Initialize components
    metrics = MetricsStore(**pg_config)
    memory = AgentMemory(
        **pg_config,
        short_term_max_tokens=20000,  # 20k for recent details
        long_term_max_tokens=30000,  # 30k for themes and patterns
    )
    library = WorkflowLibrary(DEFAULT_WORKFLOWS_DIR, metrics)

    # Copy built-in workflows if library is empty
    if BUILTIN_WORKFLOWS.exists():
        copied = library.copy_builtin_workflows(BUILTIN_WORKFLOWS)
        if copied > 0:
            print(f"  Copied {copied} built-in workflows to library.")

    # Initialize workflow engine
    store = PostgreSQLStore(**pg_config)
    await store.initialize()

    # Register custom actions
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("llm_call", LLMCallAction)
    registry.register_action("python_exec", PythonExecAction)
    registry.register_action("metrics_analyzer", MetricsAnalyzerAction)
    registry.register_action("workflow_evaluator", WorkflowEvaluatorAction)
    registry.register_action("workflow_optimizer", WorkflowOptimizerAction)

    engine = WorkflowEngine(store, registry)

    # Create agent loop
    agent = AgentLoop(
        library=library,
        engine=engine,
        metrics=metrics,
        memory=memory,
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
                elif cmd == "/memory":
                    await cmd_memory(memory)
                elif cmd == "/help":
                    cmd_help()
                elif cmd == "/dream":
                    await cmd_dream(library, engine, metrics, "anthropic")
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
