"""
Database container management commands.
"""

import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Database container management")
console = Console()

MIGRATION_DIR = Path("migration")


def _start_services(detached=True):
    """Start database services."""
    if not MIGRATION_DIR.exists():
        console.print(f"[red]Error: Migration directory not found at {MIGRATION_DIR.absolute()}[/red]")
        console.print("[dim]Make sure you're in the project root directory.[/dim]")
        raise typer.Exit(1)

    cmd = ["docker", "compose", "up"]
    if detached:
        cmd.append("-d")

    console.print("[dim]Starting database containers...[/dim]")
    result = subprocess.run(cmd, cwd=MIGRATION_DIR, capture_output=True, text=True)

    if result.returncode != 0:
        console.print(f"[red]Failed to start containers:[/red] {result.stderr}")
        raise typer.Exit(1)

    console.print("[green][OK][/green] Database containers started")
    console.print("  [dim]- PostgreSQL: localhost:15432[/dim]")
    console.print("  [dim]- Qdrant:    localhost:16333[/dim]")


@app.command()
def start(
    detached: bool = typer.Option(True, "--detach", "-d", help="Run in background"),
):
    """Start PostgreSQL and Qdrant database containers."""
    _start_services(detached)


def _stop_services(volumes=False):
    """Stop database services."""
    if not MIGRATION_DIR.exists():
        console.print(f"[red]Error: Migration directory not found[/red]")
        raise typer.Exit(1)

    cmd = ["docker", "compose", "down"]
    if volumes:
        cmd.append("-v")
        console.print("[yellow]Warning: This will remove all data volumes![/yellow]")

    console.print("[dim]Stopping database containers...[/dim]")
    result = subprocess.run(cmd, cwd=MIGRATION_DIR, capture_output=True, text=True)

    if result.returncode != 0:
        console.print(f"[red]Failed to stop containers:[/red] {result.stderr}")
        raise typer.Exit(1)

    console.print("[green][OK][/green] Database containers stopped")
    if volumes:
        console.print("[yellow]  Data volumes removed[/yellow]")


@app.command()
def stop(
    volumes: bool = typer.Option(False, "--volumes", "-v", help="Also remove data volumes (DESTRUCTIVE)"),
):
    """Stop PostgreSQL and Qdrant database containers."""
    _stop_services(volumes)


@app.command()
def restart():
    """Restart database containers."""
    _stop_services(volumes=False)
    _start_services(detached=True)
    console.print("[green][OK][/green] Database containers restarted")


def _status():
    """Show service status."""
    table = Table(title="TiMem Services")
    table.add_column("Service", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Port", style="dim")
    table.add_column("Container", style="dim")

    # Check PostgreSQL
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=timem_demo_postgres", "--format", "{{.Names}} {{.Status}}"],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            parts = result.stdout.strip().split(" ", 1)
            table.add_row("PostgreSQL", "[green]running[/green]", "15432", parts[0])
        else:
            table.add_row("PostgreSQL", "[red]stopped[/red]", "15432", "-")
    except FileNotFoundError:
        table.add_row("PostgreSQL", "[red]docker not found[/red]", "15432", "-")

    # Check Qdrant
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=timem_demo_qdrant", "--format", "{{.Names}} {{.Status}}"],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            parts = result.stdout.strip().split(" ", 1)
            table.add_row("Qdrant", "[green]running[/green]", "16333", parts[0])
        else:
            table.add_row("Qdrant", "[red]stopped[/red]", "16333", "-")
    except FileNotFoundError:
        table.add_row("Qdrant", "[red]docker not found[/red]", "16333", "-")

    console.print(table)


@app.command()
def status():
    """Show database container status."""
    _status()


@app.command()
def logs(
    service: str = typer.Argument("all", help="Service name (postgres, qdrant, or all)"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    tail: int = typer.Option(50, "--tail", "-n", help="Number of lines to show"),
):
    """View database container logs."""
    if not MIGRATION_DIR.exists():
        console.print("[red]Error: Migration directory not found[/red]")
        raise typer.Exit(1)

    cmd = ["docker", "compose", "logs", "--tail", str(tail)]
    if follow:
        cmd.append("-f")

    if service != "all":
        cmd.append(service)

    console.print(f"[dim]Showing logs for {service}...[/dim]")
    subprocess.run(cmd, cwd=MIGRATION_DIR)
