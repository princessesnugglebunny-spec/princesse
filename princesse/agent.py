"""Agent loop: think -> tool -> observe, bounded iterations."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from .context import ContextWindow
from .memory import MemoryStore
from .tools import ToolRegistry


@dataclass
class AgentResult:
    final_answer: str
    iterations: int
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, str]] = field(default_factory=list)


class Agent:
    def __init__(self, provider, tools: ToolRegistry | None = None, context: ContextWindow | None = None,
                 memory: MemoryStore | None = None, system_prompt: str = "You are a helpful agent.",
                 max_iterations: int = 10):
        self.provider = provider
        self.tools = tools or ToolRegistry.get_instance()
        self.context = context or ContextWindow()
        self.memory = memory or MemoryStore()
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations

    async def run(self, goal: str, use_optimizations: bool = True) -> AgentResult:
        self.context.append("user", goal)
        tool_calls_log: list[dict[str, Any]] = []
        final_answer = ""
        iteration = 0
        for iteration in range(self.max_iterations):
            # Get messages with optional pruning
            if use_optimizations:
                from .context_optimization import SlidingWindowCompressor
                messages = [{"role": "system", "content": self.system_prompt}]
                messages.extend(SlidingWindowCompressor.compress(self.context, keep_last=4))
            else:
                messages = [{"role": "system", "content": self.system_prompt}] + self.context.get_messages_for_model()
            
            data = await self.provider.complete(messages, self.tools.to_openai_tools())
            content, calls = self.provider.parse_response(data) if hasattr(self.provider, "parse_response") else self._parse(data)
            if calls:
                for call in calls:
                    tool_calls_log.append(call)
                async def _exec(call):
                    try:
                        r = await self.tools.execute(call["name"], call["arguments"])
                        from .context_optimization import OutputTruncator
                        result_text = json.dumps(r) if not isinstance(r, str) else r
                        return OutputTruncator.truncate_tool_output(result_text)
                    except Exception as e:
                        return f"Error: {e}"
                results = await asyncio.gather(*[_exec(c) for c in calls])
                for call, result_text in zip(calls, results):
                    self.context.append("tool", result_text, metadata={"tool": call["name"]})
                continue
            final_answer = content
            self.context.append("assistant", content)
            # if no tool calls, the model has finished - break
            break
        if not final_answer:
            final_answer = "Reached iteration limit without a final answer."
        return AgentResult(final_answer=final_answer, iterations=iteration + 1,
                           tool_calls=tool_calls_log, messages=self.context.get_messages_for_model())

    def _parse(self, data):
        choice = data["choices"][0]["message"]
        content = choice.get("content") or ""
        calls = []
        for tc in choice.get("tool_calls") or []:
            fn = tc["function"]
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            calls.append({"id": tc.get("id"), "name": fn["name"], "arguments": args})
        return content, calls


class AgentLoop:
    def __init__(self, agent: Agent):
        self.agent = agent

    async def start(self, goal: str) -> AgentResult:
        return await self.agent.run(goal)
