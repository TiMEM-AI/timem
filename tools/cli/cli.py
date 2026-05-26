"""
TiMem CLI - One-command installation and management tool.

Usage:
    timem setup       # Full interactive setup
    timem start       # Start database containers
    timem stop        # Stop database containers
    timem status      # Check service status
    timem config      # Configure environment
    timem doctor      # Run environment diagnostics
"""

import typer
from rich.console import Console

from tools.cli.commands import config, db, doctor, setup

app = typer.Typer(
    name="timem",
    help="TiMem CLI - Temporal-Hierarchical Memory System",
    add_completion=False,
)
console = Console()

# Register subcommands
app.add_typer(setup.app, name="setup", help="Interactive setup wizard")
app.add_typer(db.app, name="db", help="Database container management")
app.add_typer(config.app, name="config", help="Environment configuration")
app.add_typer(doctor.app, name="doctor", help="Environment diagnostics")


@app.callback()
def main():
    """TiMem CLI - Make Your AI Evolve Over Time"""
    pass


@app.command()
def start(
    detached: bool = typer.Option(True, "--detach", "-d", help="Run in background"),
):
    """Start TiMem database containers (alias for 'timem db start')."""
    db._start_services(detached)


@app.command()
def stop(
    volumes: bool = typer.Option(False, "--volumes", "-v", help="Also remove data volumes"),
):
    """Stop TiMem database containers (alias for 'timem db stop')."""
    db._stop_services(volumes)


@app.command()
def status():
    """Check TiMem services status (alias for 'timem db status')."""
    db._status()


if __name__ == "__main__":
    app()
