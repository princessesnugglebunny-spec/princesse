"""Code execution, terminal, and file tools for the agent."""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .tools import ToolRegistry, ToolCategory, ToolParameter


def run_terminal(command: str, cwd: str | None = None, timeout: int = 60) -> dict[str, Any]:
    try:
        proc = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return {"returncode": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "timeout"}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


def run_python(code: str, timeout: int = 30) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        proc = subprocess.run(["python3", path], capture_output=True, text=True, timeout=timeout)
        return {"returncode": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "timeout"}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def read_file(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"error": f"not found: {path}"}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        return {"path": str(p), "content": text[:20000], "size": p.stat().st_size}
    except Exception as e:
        return {"error": str(e)}


def write_file(path: str, content: str) -> dict[str, Any]:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"path": str(p), "bytes": len(content.encode())}


def edit_file(path: str, old: str, new: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"error": f"not found: {path}"}
    text = p.read_text(encoding="utf-8")
    if old not in text:
        return {"error": "old text not found"}
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    return {"path": str(p), "replaced": True}


def list_dir(path: str = ".") -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"error": f"not found: {path}"}
    entries = []
    for child in sorted(p.iterdir()):
        entries.append({"name": child.name, "type": "dir" if child.is_dir() else "file",
                       "size": child.stat().st_size if child.is_file() else None})
    return {"path": str(p), "entries": entries}


def register_execution_tools(registry=None) -> None:
    reg = registry or ToolRegistry.get_instance()
    reg.register("run_terminal", run_terminal, "Run a shell command",
                 category=ToolCategory.SYSTEM,
                 parameters=[ToolParameter(name="command", type="string", description="Shell command"),
                            ToolParameter(name="cwd", type="string", description="Working dir", required=False),
                            ToolParameter(name="timeout", type="integer", description="Timeout seconds", required=False, default=60)])
    reg.register("run_python", run_python, "Execute Python code",
                 category=ToolCategory.CODE_GENERATION,
                 parameters=[ToolParameter(name="code", type="string", description="Python code"),
                            ToolParameter(name="timeout", type="integer", description="Timeout", required=False, default=30)])
    reg.register("read_file", read_file, "Read a file",
                 category=ToolCategory.FILE_OPERATION,
                 parameters=[ToolParameter(name="path", type="string", description="File path")])
    reg.register("write_file", write_file, "Write a file",
                 category=ToolCategory.FILE_OPERATION,
                 parameters=[ToolParameter(name="path", type="string", description="File path"),
                            ToolParameter(name="content", type="string", description="Content")])
    reg.register("edit_file", edit_file, "Edit a file by replacing text",
                 category=ToolCategory.FILE_OPERATION,
                 parameters=[ToolParameter(name="path", type="string", description="File path"),
                            ToolParameter(name="old", type="string", description="Old text"),
                            ToolParameter(name="new", type="string", description="New text")])
    reg.register("list_dir", list_dir, "List directory contents",
                 category=ToolCategory.FILE_OPERATION,
                 parameters=[ToolParameter(name="path", type="string", description="Dir path", required=False, default=".")])
