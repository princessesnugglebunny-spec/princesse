"""LSP diagnostics tool: run pyright on a path and return errors."""

from __future__ import annotations

import subprocess
from typing import Any

from .tools import ToolRegistry, ToolCategory, ToolParameter


def lsp_diagnostics(path: str = ".", tool: str = "pyright") -> dict[str, Any]:
    cmd = [tool]
    if tool == "pyright":
        cmd = ["pyright", path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {"returncode": proc.returncode, "stdout": proc.stdout[-6000:], "stderr": proc.stderr[-2000:]}
    except FileNotFoundError:
        return {"error": f"{tool} not installed"}
    except Exception as e:
        return {"error": str(e)}


def register_lsp_tools(registry=None) -> None:
    reg = registry or ToolRegistry.get_instance()
    reg.register("lsp_diagnostics", lsp_diagnostics, "Run LSP/type checker diagnostics",
                 category=ToolCategory.ANALYSIS,
                 parameters=[ToolParameter(name="path", type="string", description="Path", required=False, default="."),
                            ToolParameter(name="tool", type="string", description="Tool name", required=False, default="pyright")])
