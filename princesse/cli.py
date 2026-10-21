"""CLI entrypoint for princesse."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="princesse", description="Princesse agent runtime")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("version", help="Print version")

    p_run = sub.add_parser("run", help="Run an agent on a goal")
    p_run.add_argument("goal", nargs="+", help="Goal text")
    p_run.add_argument("--provider", default="", help="Provider name (opencode, openrouter, ollama, ...)")
    p_run.add_argument("--model", default="", help="Model id")
    p_run.add_argument("--base-url", default="", help="Override provider base URL")
    p_run.add_argument("--no-boost", action="store_true", help="Disable small-model boosting")
    p_run.add_argument("--team", action="store_true", help="Use model teaming (ensemble across providers)")
    p_run.add_argument("--refresh-catalogue", action="store_true", help="Force catalogue refresh before running")

    p_explore = sub.add_parser("explore", help="Explore a codebase and populate memory")
    p_explore.add_argument("path", help="Path to explore")

    p_web = sub.add_parser("web", help="Start minimal web UI")
    p_web.add_argument("--port", type=int, default=8765)

    sub.add_parser("tui", help="Start minimal TUI")
    sub.add_parser("repl", help="Start the interactive REPL")

    p_models = sub.add_parser("models", help="Browse the model catalogue")
    p_models.add_argument("query", nargs="*", help="Search query")
    p_models.add_argument("--free", action="store_true", help="Only free models")
    p_models.add_argument("--test", action="store_true", help="Probe each listed model")
    p_models.add_argument("--provider", default="", help="Filter by provider")

    p_providers = sub.add_parser("providers", help="List providers and health")
    p_providers.add_argument("--health", action="store_true", help="Probe provider endpoints")

    p_hooks = sub.add_parser("hooks", help="List or test semantic trigger hooks")
    p_hooks.add_argument("text", nargs="*", help="Text to match against hooks")

    p_install = sub.add_parser("install", help="Install dependencies, LSP servers, and MCP servers")
    p_install.add_argument("--dry-run", action="store_true", help="Show what would be installed")

    p_reuse = sub.add_parser("reuse", help="Find existing code to reuse for a task")
    p_reuse.add_argument("task", nargs="+", help="What you intend to do")
    p_reuse.add_argument("--k", type=int, default=8, help="How many candidates")
    p_reuse.add_argument("--symbol", default="", help="Look for similar existing symbols")
    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()

    if args.cmd == "version":
        from . import __version__
        print(__version__)
        return
    if args.cmd == "run":
        asyncio.run(_run(args))
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
    if args.cmd == "repl":
        _repl()
        return
    if args.cmd == "models":
        asyncio.run(_models(args))
        return
    if args.cmd == "providers":
        _providers(args)
        return
    if args.cmd == "hooks":
        _hooks(args)
        return
    if args.cmd == "install":
        _install(args)
        return
    if args.cmd == "reuse":
        _reuse(args)
        return
    parser.print_help()


def _load_config():
    from .config import load_config
    return load_config()


def _provider_for(cfg, name: str, model: str, base_url: str):
    from .providers import OpenAICompatibleProvider, ProviderRegistry
    registry = ProviderRegistry()
    spec = registry.get(name) if name else None
    if name and spec is None:
        print(f"Unknown provider '{name}'. Known: {', '.join(sorted(registry.specs))}. Falling back to ollama.")
    if spec is None:
        spec = registry.get("ollama")
    api_key = ""
    if spec and spec.env_key:
        import os
        api_key = os.getenv(spec.env_key, "")
    url = base_url or (spec.base_url if spec else "")
    return OpenAICompatibleProvider(base_url=url, api_key=api_key, model=model or "default")


async def _run(args):
    from .agent import Agent
    from .tools import ToolRegistry
    from .bootstrap import register_default_tools
    from .bootstrap_install import EnvironmentBootstrap
    from .audit_log import AuditLog
    from .config import load_config
    from .providers import CatalogueManager
    from .small_model_booster import create_boosted_agent
    from .transparency import EventBus
    from .hooks import HookEngine

    cfg = load_config()
    audit = AuditLog(cfg.audit_log_path)
    bus = EventBus()
    hook_engine = HookEngine([Path(__file__).parent / "hooks" / "builtin", cfg.hooks_dir])

    report = EnvironmentBootstrap(cfg.workspace, audit_log=audit,
                                  install_dependencies=cfg.auto_install,
                                  install_lsp=cfg.auto_install_lsp,
                                  install_mcp=cfg.auto_install_mcp,
                                  dry_run=False).bootstrap(cfg.mcp_servers)
    if report.installed:
        print(f"Installed: {', '.join(report.installed)}")

    catalogue = CatalogueManager(cfg.catalogue_url, ttl_hours=cfg.catalogue_ttl_hours)
    await catalogue.refresh(force=args.refresh_catalogue)

    reg = ToolRegistry.get_instance()
    register_default_tools(reg)

    provider = _provider_for(cfg, args.provider, args.model, args.base_url)
    goal = " ".join(args.goal)
    agent = Agent(provider=provider, tools=reg, system_prompt="You are a helpful agent.",
                  max_iterations=cfg.max_iterations, audit_log=audit,
                  hook_engine=hook_engine, event_bus=bus)

    if args.team:
        from .providers import ModelTeam, ProviderRegistry
        registry = ProviderRegistry()
        team = ModelTeam()
        for spec in registry.available():
            if spec.cli_command:
                continue
            key, url = registry.resolve(spec.name)
            from .providers import OpenAICompatibleProvider
            p = OpenAICompatibleProvider(base_url=url, api_key=key or "", model=args.model or "default")
            team.add(spec.name, p)
        answer = await team.ensemble(goal, n=3)
        print(answer["answer"])
        return

    if cfg.boost_small_models and not args.no_boost:
        booster = create_boosted_agent(provider, reg)
        result = await booster.boosted_run(goal)
        print(result.final_answer)
    else:
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


def _repl():
    from .ui.repl import Repl
    from .tools import ToolRegistry
    from .bootstrap import register_default_tools
    from .memory import MemoryStore
    from .skills import SkillRegistry
    from .providers import CatalogueManager, ProviderRegistry
    from .hooks import HookEngine
    from .agent import Agent
    from .config import load_config
    from .transparency import EventBus

    cfg = load_config()
    reg = ToolRegistry.get_instance()
    register_default_tools(reg)
    catalogue = CatalogueManager(cfg.catalogue_url, ttl_hours=cfg.catalogue_ttl_hours)
    asyncio.run(catalogue.refresh())
    hook_engine = HookEngine([Path(__file__).parent / "hooks" / "builtin", cfg.hooks_dir])
    bus = EventBus()

    def factory():
        provider = _provider_for(cfg, cfg.provider, cfg.model, "")
        return Agent(provider=provider, tools=reg, memory=MemoryStore(),
                     system_prompt="You are a helpful agent.", max_iterations=cfg.max_iterations,
                     hook_engine=hook_engine, event_bus=bus)

    repl = Repl(agent_factory=factory, tools=reg, skills=SkillRegistry(),
                 memory=MemoryStore(), catalogue=catalogue,
                 provider_registry=ProviderRegistry(), hook_engine=hook_engine, event_bus=bus)
    asyncio.run(repl.run())


async def _models(args):
    from .providers import CatalogueManager
    from .config import load_config
    cfg = load_config()
    manager = CatalogueManager(cfg.catalogue_url, ttl_hours=cfg.catalogue_ttl_hours)
    await manager.refresh()
    catalogue = manager.get()
    if catalogue is None:
        print("Catalogue unavailable (no network and no cache).")
        return
    query = " ".join(args.query)
    if args.free:
        models = [m for m in catalogue.free_models(args.provider or None)]
        if query:
            models = [m for m in models if query.lower() in f"{m.id} {m.name}".lower()]
    elif query:
        models = catalogue.find(query, args.provider or None)
    else:
        models = catalogue.models(args.provider) if args.provider else catalogue.all_models()
    for m in models[:80]:
        flag = "free" if m.is_free else "paid"
        print(f"{m.provider}/{m.id}  ctx={m.context} {flag} tools={'yes' if m.tool_call else 'no'}")
    if args.test:
        for m in models[:10]:
            base = catalogue.base_url(m.provider) or "http://localhost:8080/v1"
            result = await manager.test_model(base, m.id)
            status = "ok" if result.get("ok") else f"fail: {result.get('reason', '')}"
            print(f"  test {m.provider}/{m.id}: {status} ({result.get('latency_ms', 0)}ms)")


def _providers(args):
    from .providers import ProviderRegistry
    registry = ProviderRegistry()
    for spec in registry.list_all():
        if spec.cli_command:
            key_state = "cli"
        elif spec.local:
            key_state = "local"
        else:
            key_state = "yes" if spec.key_present() else "no"
        line = f"{spec.name:14} {spec.display:24} {spec.base_url or '(cli)':40} {key_state}"
        print(line)
    if args.health:
        for spec in registry.list_all():
            if spec.cli_command:
                continue
            health = registry.health(spec.name)
            print(f"  {spec.name}: {'ok' if health.get('ok') else 'down'} {health.get('reason', '')}")


def _hooks(args):
    from .hooks import HookEngine
    from .config import load_config
    cfg = load_config()
    engine = HookEngine([Path(__file__).parent / "hooks" / "builtin", cfg.hooks_dir])
    text = " ".join(args.text)
    if not text:
        for hook in engine.list_all():
            triggers = ", ".join(", ".join(t.words) for t in hook.triggers)
            print(f"{hook.id:20} triggers=[{triggers}] actions={list(hook.actions)}")
        return
    for match in engine.match(text):
        print(f"{match.hook_id:20} score={match.score} matched={match.matched_words}")


def _reuse(args):
    from .reuse import ReuseAdvisor
    from .config import load_config
    cfg = load_config()
    advisor = ReuseAdvisor(root=cfg.workspace)
    advisor.build()
    if args.symbol:
        for entry in advisor.similar_symbols(args.symbol):
            print(f"{entry['score']:.2f}  {entry['path']}::{entry['symbol']}  {entry['signature']}")
        return
    task = " ".join(args.task)
    for c in advisor.suggest(task, k=args.k):
        print(f"{c.score:.3f}  {c.path}::{c.symbol} ({c.kind})  {c.signature}")
        if c.doc:
            print(f"       {c.doc.strip().splitlines()[0][:120]}")


def _install(args):
    from .bootstrap_install import EnvironmentBootstrap
    from .config import load_config
    from .audit_log import AuditLog
    cfg = load_config()
    audit = AuditLog(cfg.audit_log_path)
    report = EnvironmentBootstrap(cfg.workspace, audit_log=audit, dry_run=args.dry_run).bootstrap(cfg.mcp_servers)
    print("installed:", report.installed)
    print("skipped:", report.skipped)
    if report.failed:
        print("failed:")
        for target, error in report.failed:
            print(f"  {target}: {error}")


if __name__ == "__main__":
    main()
