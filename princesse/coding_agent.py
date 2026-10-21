"""Coding agent: solve coding tasks with test feedback loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agent import Agent
from .tools import ToolRegistry
from .execution import register_execution_tools


@dataclass
class CodeResult:
    task: str
    success: bool
    files_changed: list[str] = field(default_factory=list)
    test_output: str = ""
    final: str = ""


class CodingAgent:
    def __init__(self, provider, workspace: str | Path = ".", tools: ToolRegistry | None = None):
        self.provider = provider
        self.workspace = Path(workspace)
        self.tools = tools or ToolRegistry.get_instance()
        register_execution_tools(self.tools)
        self.workspace.mkdir(parents=True, exist_ok=True)

    async def solve(self, task: str, max_iterations: int = 8) -> CodeResult:
        system = ("You are a coding agent. Use read_file/write_file/edit_file/run_terminal/run_python "
                  "to implement the task. Run tests before finishing. Workspace: " + str(self.workspace))
        agent = Agent(provider=self.provider, tools=self.tools, system_prompt=system,
                      max_iterations=max_iterations)
        result = await agent.run(task)
        # run tests if present
        test_output = ""
        try:
            tr = await self.tools.execute("run_terminal", {"command": "python -m pytest -q", "cwd": str(self.workspace)})
            test_output = tr.get("stdout", "") + tr.get("stderr", "")
        except Exception as e:
            test_output = str(e)
        success = "failed" not in test_output.lower() and "error" not in test_output.lower()
        return CodeResult(task=task, success=success, test_output=test_output, final=result.final_answer)

    async def run_tests(self, command: str = "python -m pytest -q") -> str:
        try:
            tr = await self.tools.execute("run_terminal", {"command": command, "cwd": str(self.workspace)})
            return (tr.get("stdout", "") + "\n" + tr.get("stderr", "")).strip()
        except Exception as e:
            return str(e)


def solve_code(task: str, workspace: str = ".", provider=None) -> CodeResult:
    if provider is None:
        raise ValueError("provider required")
    ca = CodingAgent(provider=provider, workspace=workspace)
    return asyncio.run(ca.solve(task))
