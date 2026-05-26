"""
Environment diagnostics commands.
"""

import platform
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Environment diagnostics")
console = Console()


def _check_tool(name, args, min_version=None):
    """Check if a tool is installed and get its version."""
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            stdout = result.stdout.strip()
            # Try to extract version from output
            version = "found"
            for part in stdout.split():
                if any(c.isdigit() for c in part):
                    version = part.strip(",;v")
                    break
            return True, version
        return False, None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, None


@app.command()
def check():
    """Run full environment diagnostics."""
    table = Table(title="TiMem Environment Diagnostics")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details", style="dim")

    issues = []

    # Python
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 9):
        table.add_row("Python", "[green]OK[/green]", py_version)
    else:
        table.add_row("Python", "[red]FAIL[/red]", f"{py_version} (need 3.9+)")
        issues.append("Python 3.9+ required")

    # Docker
    ok, version = _check_tool("docker", ["docker", "--version"])
    if ok:
        table.add_row("Docker", "[green]OK[/green]", version)
    else:
        table.add_row("Docker", "[red]FAIL[/red]", "not found")
        issues.append("Docker not installed")

    # Docker Compose
    ok, version = _check_tool("docker compose", ["docker", "compose", "version"])
    if ok:
        table.add_row("Docker Compose", "[green]OK[/green]", version)
    else:
        ok, version = _check_tool("docker-compose", ["docker-compose", "--version"])
        if ok:
            table.add_row("Docker Compose", "[green]OK[/green]", version)
        else:
            table.add_row("Docker Compose", "[red]FAIL[/red]", "not found")
            issues.append("Docker Compose not installed")

    # Git
    ok, version = _check_tool("git", ["git", "--version"])
    if ok:
        table.add_row("Git", "[green]OK[/green]", version)
    else:
        table.add_row("Git", "[red]FAIL[/red]", "not found")
        issues.append("Git not installed")

    # Project structure
    if Path("timem").is_dir():
        table.add_row("Project Root", "[green]OK[/green]", "timem/ found")
    else:
        table.add_row("Project Root", "[red]FAIL[/red]", "timem/ not found")
        issues.append("Not in project root")

    # Virtual environment
    venv_path = Path(".venv")
    if venv_path.exists():
        table.add_row("Virtual Env", "[green]OK[/green]", ".venv exists")
    else:
        table.add_row("Virtual Env", "[yellow]WARN[/yellow]", ".venv not found")
        issues.append("Virtual environment not created")

    # .env file
    env_file = Path(".env")
    if env_file.exists():
        table.add_row("Config File", "[green]OK[/green]", ".env exists")
    else:
        table.add_row("Config File", "[yellow]WARN[/yellow]", ".env not found")
        issues.append("Configuration file missing")

    # Docker containers
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=timem_demo", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            containers = result.stdout.strip().split("\n")
            table.add_row("Containers", "[green]OK[/green]", f"{len(containers)} running")
        else:
            table.add_row("Containers", "[yellow]WARN[/yellow]", "none running")
            issues.append("Database containers not running")
    except FileNotFoundError:
        table.add_row("Containers", "[red]FAIL[/red]", "docker not available")

    console.print(table)

    # Python package imports
    console.print("\n[bold]Package Imports:[/bold]")
    packages = [
        ("asyncpg", "PostgreSQL driver"),
        ("qdrant_client", "Qdrant client"),
        ("langchain", "LangChain"),
        ("fastapi", "FastAPI"),
        ("pydantic", "Pydantic"),
    ]
    for pkg, desc in packages:
        try:
            __import__(pkg)
            console.print(f"  [green][OK][/green] {pkg} ({desc})")
        except ImportError:
            console.print(f"  [red][FAIL][/red] {pkg} ({desc}) - not installed")
            issues.append(f"Python package missing: {pkg}")

    # Summary
    if not issues:
        console.print("\n[bold green][OK] All checks passed![/bold green]")
    else:
        console.print(f"\n[yellow]Found {len(issues)} issue(s):[/yellow]")
        for issue in issues:
            console.print(f"  - {issue}")


@app.command()
def test_connection():
    """Test database connectivity."""
    console.print("[bold]Testing Database Connections...[/bold]")

    # Test PostgreSQL
    try:
        import asyncpg
        console.print("  [green][OK][/green] asyncpg import OK")
    except ImportError:
        console.print("  [red][FAIL][/red] asyncpg not installed")
        return

    # Test Qdrant
    try:
        from qdrant_client import QdrantClient
        console.print("  [green][OK][/green] qdrant-client import OK")
    except ImportError:
        console.print("  [red][FAIL][/red] qdrant-client not installed")
        return

    console.print("\n[dim]To test actual connections, ensure containers are running with 'timem start'[/dim]")
