"""
Environment configuration commands.
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Prompt

app = typer.Typer(help="Environment configuration")
console = Console()


@app.command()
def init(
    provider: str = typer.Option("openai", "--provider", "-p", help="Default LLM provider"),
    api_key: str = typer.Option(None, "--api-key", "-k", help="API key"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing .env"),
):
    """Create or update .env configuration file."""
    env_file = Path(".env")
    env_example = Path(".env.example")

    if env_file.exists() and not force:
        console.print(f"[yellow].env already exists. Use --force to overwrite.[/yellow]")
        raise typer.Exit(0)

    if not env_example.exists():
        console.print("[red].env.example not found. Cannot create .env[/red]")
        raise typer.Exit(1)

    content = env_example.read_text(encoding="utf-8")

    if not api_key:
        api_key = Prompt.ask(f"Enter your {provider.upper()} API key", password=True)

    if provider == "openai":
        content = content.replace("OPENAI_API_KEY=your_openai_key_here", f"OPENAI_API_KEY={api_key}")
    elif provider == "anthropic":
        content = content.replace("# CLAUDE_API_KEY=your_claude_key_here", f"CLAUDE_API_KEY={api_key}")
    elif provider == "zhipuai":
        content = content.replace("# ZHIPUAI_API_KEY=your_zhipuai_key_here", f"ZHIPUAI_API_KEY={api_key}")
    elif provider == "qwen":
        content = content.replace("# QWEN_API_KEY=your_qwen_key_here", f"QWEN_API_KEY={api_key}")

    env_file.write_text(content, encoding="utf-8")
    console.print(f"[green][OK][/green] Created {env_file}")


@app.command()
def show():
    """Show current configuration (sensitive values hidden)."""
    env_file = Path(".env")
    if not env_file.exists():
        console.print("[yellow].env file not found[/yellow]")
        raise typer.Exit(1)

    console.print("[bold]Current Configuration:[/bold]")
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            if "KEY" in key or "PASSWORD" in key or "SECRET" in key:
                value = "***" if value else "(not set)"
            console.print(f"  [cyan]{key}[/cyan]={value}")
