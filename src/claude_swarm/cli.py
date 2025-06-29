"""
Claude Swarm Coordinator CLI

Main command-line interface for the Claude Swarm Coordinator.
"""

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from . import __version__
from .core.coordinator import SwarmCoordinator
from .core.planner import TaskPlanner
from .core.distributor import TaskDistributor
from .evaluation.dashboard import SwarmDashboard
from .merge.strategies import SmartMerger

console = Console()


def print_version(ctx, param, value):
    """Print version and exit."""
    if not value or ctx.resilient_parsing:
        return
    console.print(f"Claude Swarm Coordinator v{__version__}")
    ctx.exit()


@click.group()
@click.option(
    "--version",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=print_version,
    help="Show version and exit.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output.",
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """
    Claude Swarm Coordinator - Orchestrate multiple Claude Code agents.
    
    A generalized framework for running multiple Claude Code agents in parallel
    to dramatically accelerate software development projects.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.argument("project_name")
@click.option(
    "--agents",
    "-a", 
    type=int,
    default=10,
    help="Number of agents to create.",
)
@click.option(
    "--description",
    "-d",
    help="Project description.",
)
@click.pass_context
def init(ctx: click.Context, project_name: str, agents: int, description: Optional[str]) -> None:
    """Initialize a new swarm project."""
    verbose = ctx.obj.get("verbose", False)
    
    try:
        coordinator = SwarmCoordinator(project_name)
        coordinator.initialize_project(
            num_agents=agents,
            description=description,
            verbose=verbose
        )
        
        console.print(Panel(
            f"✅ Project '{project_name}' initialized with {agents} agents",
            title="Success",
            border_style="green"
        ))
        
        # Show next steps
        console.print("\n📋 Next steps:")
        console.print("1. Create a requirements file (requirements.md)")
        console.print(f"2. Run: claude-swarm plan --input requirements.md")
        console.print(f"3. Run: claude-swarm launch")
        
    except Exception as e:
        console.print(Panel(
            f"❌ Failed to initialize project: {e}",
            title="Error",
            border_style="red"
        ))
        sys.exit(1)


@cli.command()
@click.option(
    "--input",
    "-i",
    "input_file",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Requirements file to analyze.",
)
@click.option(
    "--project",
    "-p",
    help="Project name (uses active project if not specified).",
)
@click.pass_context
def plan(ctx: click.Context, input_file: Path, project: Optional[str]) -> None:
    """Create task breakdown from requirements."""
    verbose = ctx.obj.get("verbose", False)
    
    try:
        if not project:
            project = SwarmCoordinator.get_active_project()
            if not project:
                console.print(Panel(
                    "❌ No active project. Use --project or run 'claude-swarm init' first.",
                    title="Error",
                    border_style="red"
                ))
                sys.exit(1)
        
        planner = TaskPlanner(project)
        planner.analyze_requirements(input_file, verbose=verbose)
        
        console.print(Panel(
            f"✅ Task plan created for project '{project}'",
            title="Success", 
            border_style="green"
        ))
        
        # Show summary
        summary = planner.get_summary()
        console.print(f"\n📊 {summary['total_tasks']} tasks created")
        console.print(f"⏱️  Estimated time: {summary['total_time']} minutes")
        console.print(f"📈 Complexity: {summary['complexity_breakdown']}")
        
    except Exception as e:
        console.print(Panel(
            f"❌ Failed to create plan: {e}",
            title="Error",
            border_style="red"
        ))
        sys.exit(1)


@cli.command()
@click.option(
    "--mode",
    type=click.Choice(["parallel", "sequential"]),
    default="parallel",
    help="Launch mode for agents.",
)
@click.option(
    "--project",
    "-p", 
    help="Project name (uses active project if not specified).",
)
@click.pass_context
def launch(ctx: click.Context, mode: str, project: Optional[str]) -> None:
    """Launch the agent swarm."""
    verbose = ctx.obj.get("verbose", False)
    
    try:
        if not project:
            project = SwarmCoordinator.get_active_project()
            if not project:
                console.print(Panel(
                    "❌ No active project. Use --project or run 'claude-swarm init' first.",
                    title="Error",
                    border_style="red"
                ))
                sys.exit(1)
        
        coordinator = SwarmCoordinator(project)
        coordinator.launch_swarm(mode=mode, verbose=verbose)
        
        console.print(Panel(
            f"🚀 Swarm launched in {mode} mode for project '{project}'",
            title="Success",
            border_style="green"
        ))
        
        # Show monitoring info
        console.print("\n📊 Monitor progress:")
        console.print("• Real-time dashboard: claude-swarm status --dashboard")
        console.print("• Quick status: claude-swarm status")
        console.print("• Merge when ready: claude-swarm merge")
        
    except Exception as e:
        console.print(Panel(
            f"❌ Failed to launch swarm: {e}",
            title="Error",
            border_style="red"
        ))
        sys.exit(1)


@cli.command()
@click.option(
    "--dashboard",
    is_flag=True,
    help="Show interactive dashboard.",
)
@click.option(
    "--project",
    "-p",
    help="Project name (uses active project if not specified).",
)
@click.pass_context
def status(ctx: click.Context, dashboard: bool, project: Optional[str]) -> None:
    """Show swarm status and progress."""
    verbose = ctx.obj.get("verbose", False)
    
    try:
        if not project:
            project = SwarmCoordinator.get_active_project()
            if not project:
                console.print(Panel(
                    "❌ No active project. Use --project or run 'claude-swarm init' first.",
                    title="Error",
                    border_style="red"
                ))
                sys.exit(1)
        
        if dashboard:
            dashboard_obj = SwarmDashboard(project)
            dashboard_obj.run()
        else:
            coordinator = SwarmCoordinator(project)
            status_info = coordinator.get_status()
            
            # Display status
            console.print(Panel(
                f"Project: {project}",
                title="📊 Swarm Status",
                border_style="blue"
            ))
            
            console.print(f"Active agents: {status_info['active_agents']}/{status_info['total_agents']}")
            console.print(f"Tasks completed: {status_info['completed_tasks']}/{status_info['total_tasks']}")
            console.print(f"Open blockers: {status_info['open_blockers']}")
            console.print(f"Recent commits: {status_info['recent_commits']}")
        
    except Exception as e:
        console.print(Panel(
            f"❌ Failed to get status: {e}",
            title="Error",
            border_style="red"
        ))
        sys.exit(1)


@cli.command()
@click.option(
    "--strategy",
    type=click.Choice(["smart", "sequential", "manual"]),
    default="smart",
    help="Merge strategy to use.",
)
@click.option(
    "--project",
    "-p",
    help="Project name (uses active project if not specified).",
)
@click.pass_context
def merge(ctx: click.Context, strategy: str, project: Optional[str]) -> None:
    """Merge completed agent work."""
    verbose = ctx.obj.get("verbose", False)
    
    try:
        if not project:
            project = SwarmCoordinator.get_active_project()
            if not project:
                console.print(Panel(
                    "❌ No active project. Use --project or run 'claude-swarm init' first.",
                    title="Error",
                    border_style="red"
                ))
                sys.exit(1)
        
        merger = SmartMerger(project)
        result = merger.execute_merge(strategy=strategy, verbose=verbose)
        
        if result['success']:
            console.print(Panel(
                f"✅ Successfully merged {result['merged_branches']} branches",
                title="Merge Complete",
                border_style="green"
            ))
            
            if result['conflicts_resolved']:
                console.print(f"🔧 Auto-resolved {result['conflicts_resolved']} conflicts")
            
            if result['manual_conflicts']:
                console.print(f"⚠️  {result['manual_conflicts']} conflicts need manual resolution")
        else:
            console.print(Panel(
                f"❌ Merge failed: {result['error']}",
                title="Merge Failed",
                border_style="red"
            ))
            sys.exit(1)
        
    except Exception as e:
        console.print(Panel(
            f"❌ Failed to merge: {e}",
            title="Error",
            border_style="red"
        ))
        sys.exit(1)


@cli.command()
@click.option(
    "--force",
    is_flag=True,
    help="Force cleanup without confirmation.",
)
@click.option(
    "--project",
    "-p",
    help="Project name (uses active project if not specified).",
)
@click.pass_context
def cleanup(ctx: click.Context, force: bool, project: Optional[str]) -> None:
    """Clean up worktrees and project data."""
    verbose = ctx.obj.get("verbose", False)
    
    try:
        if not project:
            project = SwarmCoordinator.get_active_project()
            if not project:
                console.print(Panel(
                    "❌ No active project. Use --project or run 'claude-swarm init' first.",
                    title="Error",
                    border_style="red"
                ))
                sys.exit(1)
        
        if not force:
            console.print("⚠️  This will remove all worktrees and cleanup the project.")
            if not click.confirm("Continue?"):
                console.print("Cleanup cancelled.")
                return
        
        coordinator = SwarmCoordinator(project)
        coordinator.cleanup_project(verbose=verbose)
        
        console.print(Panel(
            f"✅ Project '{project}' cleaned up successfully",
            title="Cleanup Complete",
            border_style="green"
        ))
        
    except Exception as e:
        console.print(Panel(
            f"❌ Failed to cleanup: {e}",
            title="Error",
            border_style="red"
        ))
        sys.exit(1)


@cli.command()
def docs() -> None:
    """Open documentation in browser."""
    import webbrowser
    webbrowser.open("https://claude-swarm-coordinator.readthedocs.io")
    console.print("📖 Opening documentation in browser...")


@cli.command() 
@click.argument("project_name", required=False)
def example(project_name: Optional[str]) -> None:
    """Show example project or list available examples."""
    from .utils.examples import ExampleManager
    
    manager = ExampleManager()
    
    if project_name:
        example_data = manager.get_example(project_name)
        if example_data:
            console.print(Panel(
                f"Example: {example_data['name']}",
                title="📝 Project Example",
                border_style="blue"
            ))
            console.print(example_data['description'])
            console.print(f"\nRequirements:\n{example_data['requirements']}")
        else:
            console.print(f"❌ Example '{project_name}' not found")
    else:
        examples = manager.list_examples()
        console.print(Panel(
            "Available Examples",
            title="📚 Examples",
            border_style="blue"
        ))
        for example in examples:
            console.print(f"• {example['name']}: {example['description']}")


def main() -> None:
    """Main entry point for the CLI."""
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        console.print(Panel(
            f"❌ Unexpected error: {e}",
            title="Fatal Error",
            border_style="red"
        ))
        sys.exit(1)


if __name__ == "__main__":
    main()