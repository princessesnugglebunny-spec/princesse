"""Interactive REPL with streaming output, history, and slash commands."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from ..transparency import TranscriptWriter

SLASH_COMMANDS = [
    "/help", "/exit", "/quit", "/models", "/providers", "/provider", "/model",
    "/tools", "/hooks", "/skills", "/memory", "/skills-search", "/mcp-search",
    "/doc", "/history", "/clear", "/transcript", "/events",
]


class Repl:
    def __init__(self, agent_factory, tools=None, skills=None, memory=None,
                 catalogue=None, provider_registry=None, hook_engine=None,
                 history_path: Path | str = ".princesse/history.jsonl", console: Console | None = None,
                 event_bus=None, verbose: bool = True, transcript_path: Path | str = "transcript.md"):
        self.agent_factory = agent_factory
        self.tools = tools
        self.skills = skills
        self.memory = memory
        self.catalogue = catalogue
        self.providers = provider_registry
        self.hooks = hook_engine
        self.history_path = Path(history_path)
        self.console = console or Console()
        self.agent = None
        self.event_bus = event_bus
        self.verbose = verbose
        self.transcript_path = Path(transcript_path)
        self.transcript = None
        if self.event_bus is not None:
            self.transcript = TranscriptWriter(str(self.transcript_path))
            self.transcript.attach(self.event_bus)
            if self.verbose:
                self.event_bus.subscribe(self.render_event)

    # ---------- history ----------
    def _append_history(self, kind: str, payload: str):
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            with self.history_path.open("a") as f:
                f.write(json.dumps({"kind": kind, "payload": payload}) + "\n")
        except OSError:
            pass

    def _read_history(self, limit: int = 20) -> list[str]:
        if not self.history_path.exists():
            return []
        out = []
        try:
            for line in self.history_path.read_text().splitlines()[-limit:]:
                rec = json.loads(line)
                if rec.get("kind") == "input":
                    out.append(rec.get("payload", ""))
        except Exception:
            return []
        return out

    # ---------- commands ----------
    async def handle_command(self, line: str) -> bool:
        """Handle a slash command. Returns False to exit the loop."""
        parts = line.strip().split()
        cmd = parts[0].lower()
        args = parts[1:]
        if cmd in ("/exit", "/quit"):
            return False
        if cmd == "/help":
            self._print_help()
        elif cmd == "/models":
            await self._cmd_models(args)
        elif cmd == "/providers":
            self._cmd_providers()
        elif cmd == "/provider":
            provider = getattr(self.agent, "provider", None) if self.agent else None
            self._print(f"Active provider: {getattr(provider, 'base_url', 'n/a')}")
        elif cmd == "/model":
            provider = getattr(self.agent, "provider", None) if self.agent else None
            self._print(f"Active model: {getattr(provider, 'model', 'n/a')}")
        elif cmd == "/tools":
            self._cmd_tools()
        elif cmd == "/hooks":
            self._cmd_hooks()
        elif cmd == "/skills":
            self._cmd_skills()
        elif cmd == "/skills-search":
            await self._cmd_skills_search(args)
        elif cmd == "/mcp-search":
            await self._cmd_mcp_search(args)
        elif cmd == "/memory":
            self._cmd_memory()
        elif cmd == "/doc":
            self._cmd_doc(args)
        elif cmd == "/history":
            for item in self._read_history():
                self._print(f"  {item}")
        elif cmd == "/clear":
            if self.agent is not None:
                self.agent.context.messages.clear()
            self._print("Context cleared.")
        elif cmd == "/transcript":
            if self.transcript is None:
                self._print("No transcript writer attached.")
            else:
                path = self.transcript.save()
                self._print(f"Transcript written to {path}")
        elif cmd == "/events":
            if self.event_bus is None:
                self._print("No event bus attached.")
            else:
                for event in self.event_bus.history()[-40:]:
                    self._print(f"  [{event.seq}] {event.kind} {event.data}")
        else:
            self._print(f"Unknown command: {cmd} (try /help)")
        return True

    def _print(self, text: str):
        self.console.print(text)

    # ---------- transparency rendering ----------
    def render_event(self, event) -> None:
        """Render a runtime event live so every decision is visible."""
        d = event.data
        kind = event.kind
        if kind == "agent_start":
            self.console.print(Panel(f"[bold]{d.get('goal', '')}[/bold]",
                                     title="[cyan]goal[/cyan]", border_style="cyan"))
        elif kind == "iteration":
            self.console.print(f"[dim]· iteration {d.get('index')}[/dim]")
        elif kind == "llm_call":
            self.console.print(
                f"[magenta]LLM[/magenta] {d.get('provider')} · {d.get('model')} · "
                f"{d.get('messages')} msgs · {d.get('tools')} tools offered · "
                f"[dim]{d.get('latency_ms')} ms[/dim]")
        elif kind == "llm_response":
            body = (d.get("content") or "").strip()
            calls = d.get("tool_calls") or []
            if body:
                self.console.print(f"[green]model[/green] {body[:400]}")
            for c in calls:
                self.console.print(f"[yellow]tool call[/yellow] {c.get('name')} "
                                   f"{str(c.get('arguments'))[:200]}")
        elif kind == "tool_start":
            self.console.print(f"[yellow]→ {d.get('tool')}[/yellow] {str(d.get('args'))[:200]}")
        elif kind == "tool_end":
            status = "[green]ok[/green]" if d.get("ok") else "[red]failed[/red]"
            self.console.print(f"[yellow]← {d.get('tool')}[/yellow] {status} "
                               f"[dim]{d.get('duration_ms')} ms[/dim] "
                               f"{str(d.get('result'))[:200]}")
        elif kind == "hook_match":
            self.console.print(f"[blue]hook[/blue] {d.get('hook')} matched "
                               f"(score {d.get('score')}, words {d.get('matched')})")
        elif kind == "hook_action":
            self.console.print(f"[blue]  action[/blue] {d.get('action')} → {d.get('detail')}")
        elif kind == "memory_write":
            self.console.print(f"[blue]memory[/blue] {d.get('key')}: {str(d.get('value'))[:120]}")
        elif kind == "context_update":
            self.console.print(f"[dim]context {d.get('tokens')}/{d.get('budget')} tokens, "
                               f"{d.get('messages')} messages[/dim]")
        elif kind == "agent_finish":
            self.console.print(f"[dim]finished after {d.get('iterations')} iteration(s)[/dim]")

    def _print_help(self):
        table = Table(title="Princesse REPL", show_lines=False)
        table.add_column("Command", style="cyan")
        table.add_column("Description")
        table.add_row("/help", "Show this help")
        table.add_row("/models [query]", "Browse the model catalogue")
        table.add_row("/providers", "List providers and their health")
        table.add_row("/tools", "List registered tools")
        table.add_row("/hooks", "List semantic trigger hooks")
        table.add_row("/skills", "List installed skills")
        table.add_row("/skills-search <q>", "Search the skill catalogue")
        table.add_row("/mcp-search <q>", "Search the MCP server registry")
        table.add_row("/memory", "Show stored memory")
        table.add_row("/doc <name>", "Show a module docstring")
        table.add_row("/history", "Show input history")
        table.add_row("/events", "Show raw runtime events")
        table.add_row("/transcript", "Export the session transcript")
        table.add_row("/clear", "Clear the conversation context")
        table.add_row("/exit", "Leave the REPL")
        self.console.print(table)

    async def _cmd_models(self, args: list[str]):
        if self.catalogue is None:
            self._print("No catalogue available.")
            return
        query = " ".join(args)
        catalogue = self.catalogue.get()
        if catalogue is None:
            self._print("Catalogue not loaded yet.")
            return
        models = catalogue.find(query) if query else catalogue.all_models()[:40]
        table = Table(title="Models")
        table.add_column("id", style="cyan")
        table.add_column("provider")
        table.add_column("ctx", justify="right")
        table.add_column("free", justify="center")
        table.add_column("tools", justify="center")
        for m in models[:60]:
            table.add_row(m.id, m.provider, str(m.context), "yes" if m.is_free else "",
                          "yes" if m.tool_call else "")
        self.console.print(table)

    def _cmd_providers(self):
        if self.providers is None:
            self._print("No provider registry.")
            return
        table = Table(title="Providers")
        table.add_column("name", style="cyan")
        table.add_column("label")
        table.add_column("base url")
        table.add_column("key set", justify="center")
        for spec in self.providers.list_all():
            table.add_row(spec.name, spec.display, spec.base_url or "-",
                          "yes" if spec.key_present() else "no")
        self.console.print(table)

    def _cmd_tools(self):
        if self.tools is None:
            self._print("No tool registry.")
            return
        table = Table(title="Tools")
        table.add_column("name", style="cyan")
        table.add_column("category")
        table.add_column("description")
        for entry in self.tools.list_all():
            table.add_row(entry.name, entry.category.value, entry.description[:60])
        self.console.print(table)

    def _cmd_hooks(self):
        if self.hooks is None:
            self._print("No hook engine.")
            return
        table = Table(title="Hooks")
        table.add_column("id", style="cyan")
        table.add_column("triggers")
        table.add_column("actions")
        for hook in self.hooks.list_all():
            triggers = ", ".join(", ".join(t.words) for t in hook.triggers)
            table.add_row(hook.id, triggers, ", ".join(hook.actions.keys()))
        self.console.print(table)

    def _cmd_skills(self):
        if self.skills is None:
            self._print("No skill registry.")
            return
        for skill in self.skills.list_all():
            self._print(f"  [cyan]{skill.name}[/cyan] - {skill.description}")

    async def _cmd_skills_search(self, args: list[str]):
        from ..skill_catalogue import SkillCatalogue
        catalogue = SkillCatalogue(registry=self.skills)
        results = await catalogue.search(" ".join(args))
        if not results:
            self._print("No skills matched.")
            return
        for entry in results:
            self._print(f"  [cyan]{entry.name}[/cyan] ({entry.source}) - {entry.description[:80]}")

    async def _cmd_mcp_search(self, args: list[str]):
        from ..mcp_catalogue import MCPCatalogue
        catalogue = MCPCatalogue()
        results = await catalogue.search(" ".join(args))
        if not results:
            self._print("No MCP servers matched.")
            return
        for server in results:
            self._print(f"  [cyan]{server.name}[/cyan] - {server.description[:90]}")

    def _cmd_memory(self):
        if self.memory is None:
            self._print("No memory store.")
            return
        for entry in self.memory.all()[:30]:
            self._print(f"  [cyan]{entry.key}[/cyan]: {entry.value[:100]}")

    def _cmd_doc(self, args: list[str]):
        if not args:
            self._print("Usage: /doc <module>")
            return
        import importlib
        try:
            module = importlib.import_module(args[0])
        except Exception as e:
            self._print(f"Cannot import {args[0]}: {e}")
            return
        self.console.print(Panel(module.__doc__ or "No docstring.", title=args[0]))

    # ---------- main loop ----------
    async def run(self) -> None:
        self.console.print(Panel("Princesse REPL - /help for commands, /exit to quit",
                                 title="princesse", style="cyan"))
        self.agent = self.agent_factory()
        while True:
            try:
                line = self.console.input("[bold green]princesse> [/bold green]").strip()
            except (EOFError, KeyboardInterrupt):
                self.console.print()
                break
            if not line:
                continue
            if line.startswith("/"):
                if not await self.handle_command(line):
                    break
                continue
            self._append_history("input", line)
            await self._run_agent(line)

    async def _run_agent(self, goal: str):
        if self.agent is None:
            self.agent = self.agent_factory()
        try:
            result = await self.agent.run(goal)
            self.console.print(Markdown(result.final_answer or ""))
            self._append_history("output", result.final_answer or "")
        except Exception as e:
            self.console.print(f"[red]Error:[/red] {e}")


def run_repl(**kwargs: Any):
    asyncio.run(Repl(**kwargs).run())
