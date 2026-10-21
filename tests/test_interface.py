"""Interface-layer tests: CLI, REPL, and the web UI."""

import json
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer

import pytest

from princesse.cli import _build_parser, main
from princesse.ui.repl import Repl
from princesse.ui.web import Handler


# ------------------------------------------------------------------ CLI
def test_parser_has_all_commands():
    parser = _build_parser()
    actions = [a for a in parser._actions if a.dest == "cmd"]
    assert actions
    choices = actions[0].choices or {}
    commands = set(choices)
    for expected in ("run", "explore", "web", "tui", "repl", "models", "providers",
                     "hooks", "install", "reuse", "version"):
        assert expected in commands


def test_parser_run_options():
    parser = _build_parser()
    args = parser.parse_args(["run", "do", "the", "thing", "--provider", "ollama", "--no-boost"])
    assert args.goal == ["do", "the", "thing"]
    assert args.provider == "ollama"
    assert args.no_boost is True


def test_parser_web_options():
    parser = _build_parser()
    args = parser.parse_args(["web", "--port", "9999", "--host", "0.0.0.0", "--token", "t"])
    assert args.port == 9999
    assert args.host == "0.0.0.0"
    assert args.token == "t"


def test_cli_version(capsys):
    import sys
    old = sys.argv
    sys.argv = ["princesse", "version"]
    try:
        main()
    finally:
        sys.argv = old
    assert capsys.readouterr().out.strip()


def test_cli_providers(capsys):
    from princesse.cli import _providers
    import argparse
    args = argparse.Namespace(health=False)
    _providers(args)
    out = capsys.readouterr().out
    assert "openrouter" in out
    assert "ollama" in out


def test_cli_hooks_match(capsys):
    from princesse.cli import _hooks
    import argparse
    args = argparse.Namespace(text=["the", "test", "is", "failing"])
    _hooks(args)
    out = capsys.readouterr().out
    assert "debug_session" in out


def test_cli_hooks_list(capsys):
    from princesse.cli import _hooks
    import argparse
    args = argparse.Namespace(text=[])
    _hooks(args)
    out = capsys.readouterr().out
    assert "code_review" in out


def test_cli_reuse(tmp_path, capsys, monkeypatch):
    from princesse.cli import _reuse
    import argparse
    (tmp_path / "m.py").write_text("def parse_settings(path):\n    return path\n")
    monkeypatch.setenv("PRINCESSE_WORKSPACE", str(tmp_path))
    args = argparse.Namespace(task=["parse", "settings"], k=3, symbol="")
    _reuse(args)
    out = capsys.readouterr().out
    assert "parse_settings" in out


def test_cli_install_dry_run(tmp_path, capsys):
    from princesse.cli import _install
    import argparse
    args = argparse.Namespace(dry_run=True, force=False)
    _install(args)
    out = capsys.readouterr().out
    assert "installed" in out


# ------------------------------------------------------------------ REPL
def test_repl_help_command(capsys):
    repl = Repl(agent_factory=lambda: None)
    repl.console = repl.console.__class__(width=200, force_terminal=False, record=True)
    assert asyncio_run(repl.handle_command("/help")) is True
    assert "princesse" in capsys.readouterr().out.lower()


def test_repl_exit_command():
    repl = Repl(agent_factory=lambda: None)
    assert asyncio_run(repl.handle_command("/exit")) is False


def test_repl_unknown_command(capsys):
    repl = Repl(agent_factory=lambda: None)
    assert asyncio_run(repl.handle_command("/nonsense")) is True
    assert "Unknown command" in capsys.readouterr().out


def test_repl_tools_command(capsys):
    from princesse.tools import ToolRegistry
    from princesse.bootstrap import register_default_tools
    reg = ToolRegistry()
    reg.reset()
    register_default_tools(reg)
    repl = Repl(agent_factory=lambda: None, tools=reg)
    assert asyncio_run(repl.handle_command("/tools")) is True
    assert "complexity_evaluate" in capsys.readouterr().out


def test_repl_hooks_command(capsys):
    from princesse.hooks import HookEngine
    from pathlib import Path
    engine = HookEngine([Path(__file__).parent.parent / "princesse" / "hooks" / "builtin"])
    repl = Repl(agent_factory=lambda: None, hook_engine=engine)
    assert asyncio_run(repl.handle_command("/hooks")) is True
    assert "debug_session" in capsys.readouterr().out


def test_repl_doc_command(capsys):
    repl = Repl(agent_factory=lambda: None)
    assert asyncio_run(repl.handle_command("/doc princesse.agent")) is True
    assert "Agent loop" in capsys.readouterr().out


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)


# ------------------------------------------------------------------ web
@pytest.fixture
def web_server():
    Handler.token = "secret-token"
    Handler.csrf_token = "csrf-token"
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[0], httpd.server_address[1]
    yield f"http://{host}:{port}"
    httpd.shutdown()
    httpd.server_close()


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_web_requires_token(web_server):
    status, _ = _get(f"{web_server}/api/tools")
    assert status == 401
    status, _ = _get(f"{web_server}/api/tools", {"Authorization": "Bearer secret-token"})
    assert status == 200


def test_web_tools_endpoint(web_server):
    status, body = _get(f"{web_server}/api/tools", {"Authorization": "Bearer secret-token"})
    assert status == 200
    assert "complexity_evaluate" in json.loads(body)


def test_web_run_requires_csrf(web_server):
    status, _ = _get(f"{web_server}/api/run?goal=hi", {"Authorization": "Bearer secret-token"})
    assert status == 403
    status, body = _get(f"{web_server}/api/run?goal=hi&csrf=csrf-token",
                         {"Authorization": "Bearer secret-token"})
    assert status == 200
    assert json.loads(body)["goal"] == "hi"


def test_web_index_page_contains_token(web_server):
    status, body = _get(f"{web_server}/?token=secret-token")
    assert status == 200
    assert "Princesse" in body
