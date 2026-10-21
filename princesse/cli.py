"""CLI entrypoint for princesse."""

from __future__ import annotations

import argparse
import asyncio
import sys


def main():
    parser = argparse.ArgumentParser(prog="princesse", description="Princesse agent runtime")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("version", help="Print version")
    p_run = sub.add_parser("run", help="Run an agent on a goal")
    p_run.add_argument("goal", nargs="+", help="Goal text")
    p_run.add_argument("--base-url", default="http://localhost:8080/v1")
    p_run.add_argument("--model", default="default")
    p_explore = sub.add_parser("explore", help="Explore a codebase and populate memory")
    p_explore.add_argument("path", help="Path to explore")
    p_web = sub.add_parser("web", help="Start minimal web UI")
    p_web.add_argument("--port", type=int, default=8765)
    p_tui = sub.add_parser("tui", help="Start minimal TUI")
    args = parser.parse_args()

    if args.cmd == "version":
        from . import __version__
        print(__version__)
        return
    if args.cmd == "run":
        goal = " ".join(args.goal)
        asyncio.run(_run(goal, args.base_url, args.model))
        return
    if args.cmd == "explore":
        _explore(args.path)
        return
    if args.cmd == "web":
        _web(args.port)
        return
    if args.cmd == "tui":
        _tui()
        return
    parser.print_help()


async def _run(goal, base_url, model):
    from .providers import OpenAICompatibleProvider
    from .agent import Agent
    from .tools import ToolRegistry
    from .bootstrap import register_default_tools
    reg = ToolRegistry.get_instance()
    register_default_tools(reg)
    provider = OpenAICompatibleProvider(base_url=base_url, model=model)
    agent = Agent(provider=provider, tools=reg, system_prompt="You are a helpful agent.")
    result = await agent.run(goal)
    print(result.final_answer)


def _explore(path):
    from .codebase_explore import CodebaseExplorer
    from .memory import MemoryStore
    store = MemoryStore()
    exp = CodebaseExplorer(root=path, memory=store)
    n = exp.populate_memory()
    print(f"Explored {path}: {n} symbols indexed into memory.")


def _web(port):
    from .ui.web import serve
    serve(port=port)


def _tui():
    from .ui.tui import run_tui
    run_tui()


if __name__ == "__main__":
    main()
