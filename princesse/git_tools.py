"""Git operations as agent tools."""

from __future__ import annotations

import subprocess
from typing import Any

from .tools import ToolCategory, ToolParameter, ToolRegistry, register_tool


def _run(args: list[str], cwd: str | None = None) -> dict[str, Any]:
    try:
        proc = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=60)
        return {"returncode": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


def git_status(cwd: str = ".") -> dict[str, Any]:
    return _run(["status", "--short"], cwd=cwd)


def git_diff(cwd: str = ".", staged: bool = False) -> dict[str, Any]:
    args = ["diff"]
    if staged:
        args.append("--cached")
    return _run(args, cwd=cwd)


def git_log(cwd: str = ".", n: int = 10) -> dict[str, Any]:
    return _run(["log", "--oneline", f"-{n}"], cwd=cwd)


def git_commit(message: str, cwd: str = ".", add_all: bool = False) -> dict[str, Any]:
    if add_all:
        _run(["add", "-A"], cwd=cwd)
    return _run(["commit", "-m", message], cwd=cwd)


def git_branch(name: str | None = None, cwd: str = ".") -> dict[str, Any]:
    if name:
        return _run(["checkout", "-b", name], cwd=cwd)
    return _run(["branch", "--show-current"], cwd=cwd)


def register_git_tools(registry: ToolRegistry | None = None, cwd: str = ".") -> None:
    reg = registry or ToolRegistry.get_instance()
    register_tool(reg, "git_status", lambda: git_status(cwd), "Git status",
                 category=ToolCategory.SYSTEM,
                 parameters=[])
    register_tool(reg, "git_diff", lambda staged=False: git_diff(cwd, staged), "Git diff",
                 category=ToolCategory.SYSTEM,
                 parameters=[ToolParameter(name="staged", type="boolean", description="Staged", required=False, default=False)])
    register_tool(reg, "git_log", lambda n=10: git_log(cwd, n), "Git log",
                 category=ToolCategory.SYSTEM,
                 parameters=[ToolParameter(name="n", type="integer", description="Count", required=False, default=10)])
    register_tool(reg, "git_commit", lambda message, add_all=False: git_commit(message, cwd, add_all), "Git commit",
                 category=ToolCategory.SYSTEM,
                 parameters=[ToolParameter(name="message", type="string", description="Message"),
                            ToolParameter(name="add_all", type="boolean", description="Add all", required=False, default=False)])
    register_tool(reg, "git_branch", lambda name=None: git_branch(name, cwd), "Git branch",
                 category=ToolCategory.SYSTEM,
                 parameters=[ToolParameter(name="name", type="string", description="Branch name", required=False)])
