"""Automatic environment setup: dependencies, LSP servers, and MCP servers."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LSP_SERVERS: dict[str, dict[str, Any]] = {
    "python": {"command": "pyright", "install": ["pip", "install", "pyright"], "check": "pyright --version"},
    "typescript": {"command": "typescript-language-server", "install": ["npm", "install", "-g", "typescript-language-server typescript"], "check": "typescript-language-server --version"},
    "rust": {"command": "rust-analyzer", "install": None, "check": "rust-analyzer --version"},
    "go": {"command": "gopls", "install": ["go", "install", "golang.org/x/tools/gopls@latest"], "check": "gopls version"},
    "c": {"command": "clangd", "install": None, "check": "clangd --version"},
    "cpp": {"command": "clangd", "install": None, "check": "clangd --version"},
    "java": {"command": "jdtls", "install": None, "check": "jdtls --version"},
    "ruby": {"command": "solargraph", "install": ["gem", "install", "solargraph"], "check": "solargraph --version"},
    "php": {"command": "intelephense", "install": ["npm", "install", "-g", "intelephense"], "check": "intelephense --version"},
}

LANGUAGE_BY_EXTENSION = {
    ".py": "python", ".pyi": "python",
    ".ts": "typescript", ".tsx": "typescript", ".js": "typescript", ".jsx": "typescript",
    ".rs": "rust", ".go": "go", ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
    ".java": "java", ".rb": "ruby", ".php": "php",
}


@dataclass
class InstallReport:
    installed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"installed": self.installed, "skipped": self.skipped,
                "failed": [{"target": t, "error": e} for t, e in self.failed]}


def _run(cmd: list[str], timeout: int = 300, cwd: str | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return proc.returncode, (proc.stdout + proc.stderr)[-2000:]
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"
    except Exception as e:
        return 1, str(e)


class EnvironmentBootstrap:
    """Installs missing dependencies, LSP servers, and MCP servers on demand."""

    def __init__(self, project_root: Path | str = ".", audit_log=None,
                 install_dependencies: bool = True, install_lsp: bool = True,
                 install_mcp: bool = True, dry_run: bool = False,
                 state_path: Path | str = "~/.princesse/bootstrap.json",
                 interval_hours: float = 24.0):
        self.project_root = Path(project_root)
        self.audit_log = audit_log
        self.install_dependencies = install_dependencies
        self.install_lsp = install_lsp
        self.install_mcp = install_mcp
        self.dry_run = dry_run
        self.state_path = Path(state_path).expanduser()
        self.interval_hours = interval_hours

    def _log(self, kind: str, target: str, command: str, ok: bool):
        if self.audit_log:
            self.audit_log.log_install(kind, target, command, ok)

    def ensure_dependencies(self, report: InstallReport | None = None) -> InstallReport:
        """Install the project itself when its imports are not resolvable."""
        report = report or InstallReport()
        if not self.install_dependencies:
            report.skipped.append("dependencies")
            return report
        if self._imports_resolve():
            report.skipped.append("dependencies")
            return report
        cmd = [sys.executable, "-m", "pip", "install", "-e", str(self.project_root)]
        if self.dry_run:
            report.skipped.append("dependencies (dry-run)")
            return report
        code, out = _run(cmd)
        self._log("dependency", "project", " ".join(cmd), code == 0)
        if code == 0:
            report.installed.append("dependencies")
        else:
            report.failed.append(("dependencies", out[:300]))
        return report

    def _imports_resolve(self) -> bool:
        req = self.project_root / "pyproject.toml"
        if not req.exists():
            return True
        try:
            import tomllib
            data = tomllib.loads(req.read_text())
        except Exception:
            return True
        deps = data.get("project", {}).get("dependencies", []) or []
        for dep in deps:
            name = dep.split(">=")[0].split("==")[0].split("[")[0].split("~")[0].strip()
            if not name:
                continue
            module = name.replace("-", "_")
            if module in ("pyyaml", "yaml"):
                module = "yaml"
            try:
                __import__(module)
            except ImportError:
                return False
        return True

    def detect_languages(self, root: Path | str | None = None) -> list[str]:
        root = Path(root or self.project_root)
        found = set()
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in LANGUAGE_BY_EXTENSION:
                found.add(LANGUAGE_BY_EXTENSION[path.suffix])
        return sorted(found)

    def ensure_lsp(self, languages: list[str] | None = None,
                   report: InstallReport | None = None) -> InstallReport:
        report = report or InstallReport()
        if not self.install_lsp:
            report.skipped.append("lsp")
            return report
        langs = languages if languages is not None else self.detect_languages()
        for lang in langs:
            spec = LSP_SERVERS.get(lang)
            if not spec:
                report.skipped.append(f"lsp:{lang}")
                continue
            if shutil.which(spec["command"]):
                report.skipped.append(f"lsp:{lang}")
                continue
            install = spec.get("install")
            if not install:
                report.skipped.append(f"lsp:{lang} (no installer)")
                continue
            if self.dry_run:
                report.skipped.append(f"lsp:{lang} (dry-run)")
                continue
            code, out = _run(install)
            self._log("lsp", lang, " ".join(install), code == 0)
            if code == 0:
                report.installed.append(f"lsp:{lang}")
            else:
                report.failed.append((f"lsp:{lang}", out[:300]))
        return report

    def ensure_mcp(self, servers: list[str] | None = None,
                   report: InstallReport | None = None) -> InstallReport:
        """Connect MCP servers declared in config (uvx/npx commands)."""
        report = report or InstallReport()
        if not self.install_mcp:
            report.skipped.append("mcp")
            return report
        for entry in servers or []:
            cmd = entry if isinstance(entry, list) else entry.split()
            if not cmd:
                continue
            if shutil.which(cmd[0]) or self.dry_run:
                report.skipped.append(f"mcp:{cmd[0]}")
                continue
            install = ["npm", "install", "-g", cmd[0]] if cmd[0] in ("npx", "npm") else None
            if install is None:
                report.skipped.append(f"mcp:{cmd[0]}")
                continue
            code, out = _run(install)
            self._log("mcp", cmd[0], " ".join(install), code == 0)
            if code == 0:
                report.installed.append(f"mcp:{cmd[0]}")
            else:
                report.failed.append((f"mcp:{cmd[0]}", out[:300]))
        return report

    def _state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text())
        except Exception:
            return {}

    def _save_state(self, state: dict[str, Any]):
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(state, indent=2))
        except OSError:
            pass

    def recently_ran(self) -> bool:
        """True when the bootstrap ran within the configured interval."""
        import time
        state = self._state()
        last = state.get("last_run", 0)
        if not last:
            return False
        return (time.time() - last) < self.interval_hours * 3600

    def bootstrap(self, mcp_servers: list[str] | None = None, force: bool = False) -> InstallReport:
        report = InstallReport()
        if not force and self.recently_ran():
            report.skipped.append("bootstrap (ran recently)")
            return report
        self.ensure_dependencies(report)
        self.ensure_lsp(report=report)
        self.ensure_mcp(mcp_servers, report=report)
        import time
        state = self._state()
        state["last_run"] = time.time()
        state["installed"] = report.installed
        self._save_state(state)
        return report


def read_mcp_config(path: Path | str) -> list[list[str]]:
    """Read MCP server launch commands from a JSON config file."""
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
    except Exception:
        return []
    servers = data.get("mcpServers") or data.get("mcp_servers") or {}
    out = []
    if isinstance(servers, dict):
        for cfg in servers.values():
            if isinstance(cfg, dict) and cfg.get("command"):
                out.append([cfg["command"], *(cfg.get("args") or [])])
    return out
