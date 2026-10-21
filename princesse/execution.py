"""Code execution, terminal, and file tools (workspace-sandboxed)."""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .security import CommandPolicy, PathEscapeError, safe_path
from .tools import ToolRegistry, ToolCategory, ToolParameter, register_tool


@dataclass
class ExecutionContext:
    """Holds the workspace root and command policy used by execution tools."""
    root: Path = field(default_factory=lambda: Path.cwd())
    policy: CommandPolicy = field(default_factory=CommandPolicy)
    timeout: int = 60

    def resolve(self, path: str) -> Path:
        return safe_path(path, self.root)


def _default_context() -> ExecutionContext:
    return ExecutionContext(root=Path.cwd())


def run_terminal(command: str, cwd: str | None = None, timeout: int = 60,
                 context: ExecutionContext | None = None) -> dict[str, Any]:
    ctx = context or _default_context()
    try:
        ctx.policy.validate(command)
    except PermissionError as e:
        return {"returncode": -1, "stdout": "", "stderr": f"blocked: {e}"}
    workdir = str(ctx.root)
    if cwd:
        try:
            workdir = str(ctx.resolve(cwd))
        except PathEscapeError as e:
            return {"returncode": -1, "stdout": "", "stderr": f"blocked: {e}"}
    try:
        # shell=True is deliberate: the tool takes a shell command. The command is
        # gated by CommandPolicy (allowlist + deny patterns) and runs inside the
        # workspace sandbox, which is the mitigation bandit cannot see.
        proc = subprocess.run(command, shell=True, cwd=workdir, capture_output=True,  # nosec B602
                              text=True, timeout=timeout or ctx.timeout)
        return {"returncode": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "timeout"}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


def run_python(code: str, timeout: int = 30, context: ExecutionContext | None = None) -> dict[str, Any]:
    ctx = context or _default_context()
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, dir=str(ctx.root)) as f:
        f.write(code)
        path = f.name
    try:
        proc = subprocess.run(["python3", path], capture_output=True, text=True, timeout=timeout,
                              cwd=str(ctx.root))
        return {"returncode": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "timeout"}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def read_file(path: str, context: ExecutionContext | None = None) -> dict[str, Any]:
    ctx = context or _default_context()
    try:
        p = ctx.resolve(path)
    except PathEscapeError as e:
        return {"error": str(e)}
    if not p.exists():
        return {"error": f"not found: {path}"}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        return {"path": str(p), "content": text[:20000], "size": p.stat().st_size}
    except Exception as e:
        return {"error": str(e)}


def write_file(path: str, content: str, context: ExecutionContext | None = None) -> dict[str, Any]:
    ctx = context or _default_context()
    try:
        p = ctx.resolve(path)
    except PathEscapeError as e:
        return {"error": str(e)}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"path": str(p), "bytes": len(content.encode())}
    except Exception as e:
        return {"error": str(e)}


def edit_file(path: str, old: str, new: str, context: ExecutionContext | None = None) -> dict[str, Any]:
    ctx = context or _default_context()
    try:
        p = ctx.resolve(path)
    except PathEscapeError as e:
        return {"error": str(e)}
    if not p.exists():
        return {"error": f"not found: {path}"}
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as e:
        return {"error": str(e)}
    if old not in text:
        return {"error": "old text not found"}
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    return {"path": str(p), "replaced": True}


def list_dir(path: str = ".", context: ExecutionContext | None = None) -> dict[str, Any]:
    ctx = context or _default_context()
    try:
        p = ctx.resolve(path)
    except PathEscapeError as e:
        return {"error": str(e)}
    if not p.exists():
        return {"error": f"not found: {path}"}
    entries = []
    for child in sorted(p.iterdir()):
        entries.append({"name": child.name, "type": "dir" if child.is_dir() else "file",
                        "size": child.stat().st_size if child.is_file() else None})
    return {"path": str(p), "entries": entries}


def register_execution_tools(registry: ToolRegistry | None = None,
                             context: ExecutionContext | None = None) -> ToolRegistry:
    reg = registry or ToolRegistry.get_instance()
    ctx = context or _default_context()
    register_tool(reg, "run_terminal", lambda command, cwd=None, timeout=60: run_terminal(command, cwd, timeout, ctx),
                 "Run a shell command inside the workspace (allowlisted)",
                 category=ToolCategory.SYSTEM,
                 parameters=[ToolParameter(name="command", type="string", description="Shell command"),
                            ToolParameter(name="cwd", type="string", description="Working dir", required=False),
                            ToolParameter(name="timeout", type="integer", description="Timeout seconds", required=False, default=60)])
    register_tool(reg, "run_python", lambda code, timeout=30: run_python(code, timeout, ctx),
                 "Execute Python code inside the workspace",
                 category=ToolCategory.CODE_GENERATION,
                 parameters=[ToolParameter(name="code", type="string", description="Python code"),
                            ToolParameter(name="timeout", type="integer", description="Timeout", required=False, default=30)])
    register_tool(reg, "read_file", lambda path: read_file(path, ctx),
                 "Read a file inside the workspace",
                 category=ToolCategory.FILE_OPERATION,
                 parameters=[ToolParameter(name="path", type="string", description="File path")])
    register_tool(reg, "write_file", lambda path, content: write_file(path, content, ctx),
                 "Write a file inside the workspace",
                 category=ToolCategory.FILE_OPERATION,
                 parameters=[ToolParameter(name="path", type="string", description="File path"),
                            ToolParameter(name="content", type="string", description="Content")])
    register_tool(reg, "edit_file", lambda path, old, new: edit_file(path, old, new, ctx),
                 "Edit a file by replacing text",
                 category=ToolCategory.FILE_OPERATION,
                 parameters=[ToolParameter(name="path", type="string", description="File path"),
                            ToolParameter(name="old", type="string", description="Old text"),
                            ToolParameter(name="new", type="string", description="New text")])
    register_tool(reg, "list_dir", lambda path=".": list_dir(path, ctx),
                 "List directory contents inside the workspace",
                 category=ToolCategory.FILE_OPERATION,
                 parameters=[ToolParameter(name="path", type="string", description="Dir path", required=False, default=".")])
    return reg
