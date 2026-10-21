"""Minimal TUI using rich."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel


def run_tui():
    console = Console()
    console.print(Panel("Princesse TUI\nType 'quit' to exit.", title="Princesse"))
    while True:
        try:
            line = console.input("[bold green]princesse> [/bold green]")
        except (EOFError, KeyboardInterrupt):
            break
        if line.strip().lower() in {"quit", "exit", "q"}:
            break
        console.print(f"[cyan]echo:[/cyan] {line}")
