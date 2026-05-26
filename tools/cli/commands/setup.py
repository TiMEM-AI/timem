"""
TiMem Setup Wizard - Interactive one-line installation.
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt

app = typer.Typer(help="Interactive setup wizard")
console = Console()

MIGRATION_DIR = Path("migration")
REQUIRED_TOOLS = {
    "python": ("Python", "3.9", lambda: _check_python()),
    "docker": ("Docker", "20.10", lambda: _check_docker()),
    "docker-compose": ("Docker Compose", "2.0", lambda: _check_docker_compose()),
    "git": ("Git", "2.20", lambda: _check_git()),
}


def _check_python():
    """Check Python version."""
    version = sys.version_info
    return f"{version.major}.{version.minor}.{version.micro}"


def _check_docker():
    """Check Docker version."""
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True, text=True, check=True
        )
        # Parse: Docker version 24.0.7, build ...
        parts = result.stdout.strip().split()
        for i, part in enumerate(parts):
            if part.lower() == "version" and i + 1 < len(parts):
                return parts[i + 1].rstrip(",")
        return "unknown"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _check_docker_compose():
    """Check Docker Compose version."""
    try:
        # Try docker compose (v2)
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True, text=True, check=True
        )
        parts = result.stdout.strip().split()
        for i, part in enumerate(parts):
            if part.lower() == "version" and i + 1 < len(parts):
                return parts[i + 1].rstrip(",")
        return "unknown"
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            # Try docker-compose (v1)
            result = subprocess.run(
                ["docker-compose", "--version"],
                capture_output=True, text=True, check=True
            )
            parts = result.stdout.strip().split()
            for i, part in enumerate(parts):
                if part.lower() == "version" and i + 1 < len(parts):
                    return parts[i + 1].rstrip(",")
            return "unknown"
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None


def _check_git():
    """Check Git version."""
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True, text=True, check=True
        )
        parts = result.stdout.strip().split()
        return parts[-1] if parts else "unknown"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _version_satisfies(current, required):
    """Check if current version meets minimum requirement."""
    if current is None:
        return False
    try:
        current_parts = [int(x) for x in current.split(".")[:2]]
        required_parts = [int(x) for x in required.split(".")[:2]]
        return current_parts >= required_parts
    except (ValueError, IndexError):
        return True  # If we can't parse, assume ok


def _run_command(cmd, cwd=None, check=True):
    """Run a shell command and return result."""
    console.print(f"[dim]$ {' '.join(cmd)}[/dim]")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        console.print(f"[red]Error: {result.stderr}[/red]")
        raise subprocess.CalledProcessError(result.returncode, cmd)
    return result


@app.command()
def wizard(
    skip_checks: bool = typer.Option(False, "--skip-checks", help="Skip prerequisite checks"),
    skip_deps: bool = typer.Option(False, "--skip-deps", help="Skip dependency installation"),
    skip_db: bool = typer.Option(False, "--skip-db", help="Skip database setup"),
):
    """
    Run the full TiMem setup wizard interactively.
    """
    console.print(Panel.fit(
        "[bold cyan]TiMem Setup Wizard[/bold cyan]\n"
        "[dim]Temporal-Hierarchical Memory System[/dim]",
        border_style="cyan"
    ))

    # Step 1: Prerequisites Check
    if not skip_checks:
        console.print("\n[bold]Step 1/5: Checking Prerequisites[/bold]")
        all_ok = True
        for tool, (name, min_version, checker) in REQUIRED_TOOLS.items():
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
                task = progress.add_task(f"Checking {name}...", total=None)
                version = checker()
            if version and _version_satisfies(version, min_version):
                console.print(f"  [green][OK][/green] {name} {version}")
            elif version:
                console.print(f"  [yellow][WARN][/yellow] {name} {version} (requires {min_version}+)")
                all_ok = False
            else:
                console.print(f"  [red][FAIL][/red] {name} not found (requires {min_version}+)")
                all_ok = False

        if not all_ok:
            console.print("\n[red]Some prerequisites are missing. Please install them first.[/red]")
            console.print("[dim]See: https://github.com/TiMEM-AI/timem-ai#prerequisites[/dim]")
            if not Confirm.ask("Continue anyway?", default=False):
                raise typer.Exit(1)

    # Step 2: Virtual Environment
    if not skip_deps:
        console.print("\n[bold]Step 2/5: Setting Up Python Environment[/bold]")
        venv_path = Path(".venv")
        if venv_path.exists():
            console.print("  [yellow][!][/yellow] Virtual environment already exists at .venv")
            if not Confirm.ask("Reuse existing environment?", default=True):
                shutil.rmtree(venv_path)
                _run_command([sys.executable, "-m", "venv", ".venv"])
                console.print("  [green][OK][/green] Created new virtual environment")
        else:
            _run_command([sys.executable, "-m", "venv", ".venv"])
            console.print("  [green][OK][/green] Created virtual environment")

        # Install dependencies
        console.print("\n  Installing dependencies...")
        pip_cmd = str(venv_path / ("Scripts" if platform.system() == "Windows" else "bin") / "pip")
        _run_command([pip_cmd, "install", "-r", "requirements.txt"])
        console.print("  [green][OK][/green] Dependencies installed")
    else:
        console.print("\n[dim]Skipping dependency installation.[/dim]")

    # Step 3: Database Setup
    if not skip_db:
        console.print("\n[bold]Step 3/5: Starting Database Containers[/bold]")
        if not MIGRATION_DIR.exists():
            console.print(f"  [red][FAIL][/red] Migration directory not found: {MIGRATION_DIR}")
            raise typer.Exit(1)

        # Check if already running
        try:
            result = subprocess.run(
                ["docker", "compose", "ps", "--format", "json"],
                cwd=MIGRATION_DIR, capture_output=True, text=True
            )
            if "timem_demo_postgres" in result.stdout or "timem_demo_qdrant" in result.stdout:
                console.print("  [yellow][!][/yellow] TiMem containers already running")
                if not Confirm.ask("Restart containers?", default=False):
                    console.print("  [dim]Using existing containers[/dim]")
                    skip_db = True
        except Exception:
            pass

        if not skip_db:
            _run_command(["docker", "compose", "up", "-d"], cwd=MIGRATION_DIR)
            console.print("  [green][OK][/green] Database containers started")
            console.print("  [dim]  - PostgreSQL: localhost:15432[/dim]")
            console.print("  [dim]  - Qdrant: localhost:16333[/dim]")

            # Wait for databases to be ready
            console.print("\n  Waiting for databases to be ready...")
            import time
            time.sleep(5)
            console.print("  [green][OK][/green] Databases should be ready (verify with 'timem doctor')")
    else:
        console.print("\n[dim]Skipping database setup.[/dim]")

    # Step 4: Environment Configuration
    console.print("\n[bold]Step 4/5: Environment Configuration[/bold]")
    env_file = Path(".env")
    env_example = Path(".env.example")

    if env_file.exists():
        console.print("  [yellow][!][/yellow] .env file already exists")
        if not Confirm.ask("Overwrite .env file?", default=False):
            console.print("  [dim]Keeping existing .env[/dim]")
        else:
            _create_env(env_example, env_file)
    else:
        if env_example.exists():
            _create_env(env_example, env_file)
        else:
            console.print("  [red][FAIL][/red] .env.example not found")
            console.print("  [dim]Please create .env manually[/dim]")

    # Step 5: Verification
    console.print("\n[bold]Step 5/5: Installation Verification[/bold]")
    try:
        venv_python = Path(".venv") / ("Scripts" if platform.system() == "Windows" else "bin") / "python"
        result = subprocess.run(
            [str(venv_python), "-c", "from timem import AsyncMemory; print('OK')"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            console.print("  [green][OK][/green] TiMem SDK imports successfully")
        else:
            console.print(f"  [red][FAIL][/red] Import check failed: {result.stderr}")
    except Exception as e:
        console.print(f"  [yellow][!][/yellow] Could not verify: {e}")

    # Summary
    console.print("\n" + Panel.fit(
        "[bold green]Setup Complete![/bold green]\n\n"
        "[bold]Quick Commands:[/bold]\n"
        "  timem start       Start database containers\n"
        "  timem stop        Stop database containers\n"
        "  timem status      Check service status\n"
        "  timem doctor      Run diagnostics\n\n"
        "[bold]Next Steps:[/bold]\n"
        "  1. Edit .env to add your API keys\n"
        "  2. Run examples: python cloud-service/examples/01_quick_start.py\n"
        "  3. Read docs: https://github.com/TiMEM-AI/timem-ai",
        border_style="green"
    ))


def _create_env(source: Path, target: Path):
    """Create .env file interactively."""
    if not source.exists():
        console.print("  [red][FAIL][/red] Source template not found")
        return

    # Read template
    content = source.read_text(encoding="utf-8")

    # Ask for API key
    console.print("  [dim]Configure your LLM API key:[/dim]")
    provider = Prompt.ask(
        "Select LLM provider",
        choices=["openai", "anthropic", "zhipuai", "qwen", "skip"],
        default="openai"
    )

    if provider != "skip":
        key = Prompt.ask(f"Enter your {provider.upper()} API key", password=True)
        if provider == "openai":
            content = content.replace("OPENAI_API_KEY=your_openai_key_here", f"OPENAI_API_KEY={key}")
        elif provider == "anthropic":
            content = content.replace("# CLAUDE_API_KEY=your_claude_key_here", f"CLAUDE_API_KEY={key}")
        elif provider == "zhipuai":
            content = content.replace("# ZHIPUAI_API_KEY=your_zhipuai_key_here", f"ZHIPUAI_API_KEY={key}")
        elif provider == "qwen":
            content = content.replace("# QWEN_API_KEY=your_qwen_key_here", f"QWEN_API_KEY={key}")

    target.write_text(content, encoding="utf-8")
    console.print(f"  [green][OK][/green] Created {target}")


@app.command()
def quick(
    provider: str = typer.Option("openai", "--provider", "-p", help="LLM provider (openai, anthropic, zhipuai, qwen)"),
    api_key: str = typer.Option(None, "--api-key", "-k", help="API key (will prompt if not provided)"),
):
    """
    Quick one-line setup with minimal interaction.
    """
    console.print("[bold cyan]TiMem Quick Setup[/bold cyan]\n")

    # Auto-detect and run steps with defaults
    if not Path(".venv").exists():
        console.print("[dim]Creating virtual environment...[/dim]")
        _run_command([sys.executable, "-m", "venv", ".venv"])

    pip_cmd = str(Path(".venv") / ("Scripts" if platform.system() == "Windows" else "bin") / "pip")

    console.print("[dim]Installing dependencies...[/dim]")
    _run_command([pip_cmd, "install", "-r", "requirements.txt"])

    if not api_key:
        api_key = Prompt.ask(f"Enter your {provider.upper()} API key", password=True)

    # Create .env
    env_example = Path(".env.example")
    env_file = Path(".env")
    if env_example.exists():
        content = env_example.read_text(encoding="utf-8")
        if provider == "openai":
            content = content.replace("OPENAI_API_KEY=your_openai_key_here", f"OPENAI_API_KEY={api_key}")
        elif provider == "anthropic":
            content = content.replace("# CLAUDE_API_KEY=your_claude_key_here", f"CLAUDE_API_KEY={api_key}")
        elif provider == "zhipuai":
            content = content.replace("# ZHIPUAI_API_KEY=your_zhipuai_key_here", f"ZHIPUAI_API_KEY={api_key}")
        elif provider == "qwen":
            content = content.replace("# QWEN_API_KEY=your_qwen_key_here", f"QWEN_API_KEY={api_key}")
        env_file.write_text(content, encoding="utf-8")

    # Start databases
    if MIGRATION_DIR.exists():
        console.print("[dim]Starting database containers...[/dim]")
        _run_command(["docker", "compose", "up", "-d"], cwd=MIGRATION_DIR)

    console.print("\n[bold green][OK] Quick setup complete![/bold green]")
    console.print("[dim]Run 'timem status' to verify, or 'timem doctor' for diagnostics.[/dim]")
