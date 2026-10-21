"""Subagent delegation: spawn isolated agents with own context."""

from __future__ import annotations

import asyncio
from typing import Any

from .agent import Agent
from .context import ContextWindow
from .memory import MemoryStore
from .tools import ToolRegistry


class DelegationManager:
    def __init__(self, provider_factory, tools: ToolRegistry | None = None, system_prompt: str = ""):
        self.provider_factory = provider_factory
        self.tools = tools
        self.system_prompt = system_prompt

    async def spawn(self, goal: str, name: str = "subagent") -> dict[str, Any]:
        provider = self.provider_factory()
        agent = Agent(provider=provider, tools=self.tools or ToolRegistry.get_instance(),
                      context=ContextWindow(session_id=name), memory=MemoryStore(),
                      system_prompt=self.system_prompt or "You are a focused subagent.")
        result = await agent.run(goal)
        return {"name": name, "final_answer": result.final_answer, "iterations": result.iterations}

    async def spawn_parallel(self, goals: list[str]) -> list[dict[str, Any]]:
        tasks = [self.spawn(g, name=f"subagent_{i}") for i, g in enumerate(goals)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if not isinstance(r, BaseException)]

    def register_tools(self, registry=None) -> None:
        from .tools import ToolRegistry, ToolCategory, ToolParameter
        reg = registry or ToolRegistry.get_instance()

        async def delegate(goal: str) -> dict[str, Any]:
            return await self.spawn(goal)

        reg.register("delegate_task", delegate, "Delegate a task to a subagent",
                     category=ToolCategory.SYSTEM,
                     parameters=[ToolParameter(name="goal", type="string", description="Task goal")])
