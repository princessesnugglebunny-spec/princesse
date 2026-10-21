"""Agent loop: think -> tool -> observe, bounded iterations."""

from __future__ import annotations

import asyncio
import json
import time
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
                 max_iterations: int = 10, hook_engine=None, hook_executor=None,
                 audit_log=None, team=None, event_bus=None, stream_enabled: bool = False):
        self.provider = provider
        self.tools = tools or ToolRegistry.get_instance()
        self.context = context or ContextWindow()
        self.memory = memory or MemoryStore()
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.hook_engine = hook_engine
        self.hook_executor = hook_executor
        self.audit_log = audit_log
        self.team = team
        self.event_bus = event_bus
        self.stream_enabled = stream_enabled
        self.hook_matches: list[Any] = []
        self.active_tools: set[str] | None = None
        self.always_tools: set[str] = set()

    def _apply_hooks(self, text: str) -> str:
        """Match hooks against text and apply their actions. Returns extra prompt text."""
        if self.hook_engine is None:
            return ""
        matches = self.hook_engine.match(text)
        self.hook_matches = matches
        if self.event_bus:
            for match in matches:
                self.event_bus.hook_match(match.hook_id, match.score, match.matched_words)
        if not matches:
            return ""
        if self.hook_executor is not None:
            outcome = self.hook_executor.apply(matches)
            if self.event_bus:
                for action in outcome.applied:
                    self.event_bus.hook_action(action.split(":")[0], action.split(":")[-1])
            # scope the advertised tool set to what the hooks preloaded (token saving)
            preloaded: set[str] = set()
            for key, detail in outcome.details.items():
                if key.endswith(":preload_tools") and isinstance(detail, list):
                    preloaded.update(detail)
            if preloaded:
                self.active_tools = preloaded | self.always_tools
            return self.hook_executor.prompt_injection(matches)
        return ""

    async def run(self, goal: str, use_optimizations: bool = True) -> AgentResult:
        self.context.append("user", goal)
        extra_prompt = self._apply_hooks(goal)
        if self.event_bus:
            self.event_bus.agent_start(goal, provider=getattr(self.provider, "model", "unknown"))
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
            if extra_prompt:
                messages.insert(1, {"role": "system", "content": extra_prompt})
            if self.active_tools is not None:
                names = ", ".join(sorted(self.active_tools))
                messages.insert(1, {"role": "system",
                                    "content": f"Tools available for this task: {names}. "
                                               f"Call only these."})

            provider = self.provider
            if self.team is not None and self.team.members:
                member = self.team.route(goal)
                if member is not None:
                    provider = member.provider
            started = time.monotonic()
            if self.event_bus:
                self.event_bus.iteration(iteration + 1)
                self.event_bus.llm_call(
                    provider=getattr(self.provider, "base_url", "unknown"),
                    model=getattr(self.provider, "model", "unknown"),
                    messages=len(messages),
                    tools=len(self.tools.to_openai_tools(self.active_tools)),
                    latency_ms=(time.monotonic() - started) * 1000)
            if self.stream_enabled and hasattr(provider, "stream"):
                content, calls = await self._stream_complete(provider, messages)
            else:
                data = await provider.complete(messages, self.tools.to_openai_tools(self.active_tools))
                if self.audit_log:
                    self.audit_log.log_llm_call(
                        model=getattr(self.provider, "model", "unknown"),
                        provider=getattr(self.provider, "base_url", "unknown"),
                        latency_ms=(time.monotonic() - started) * 1000)
                content, calls = (provider.parse_response(data) if hasattr(provider, "parse_response")
                                  else self._parse(data))
            if self.event_bus:
                self.event_bus.llm_response(content, calls)
            if calls:
                for call in calls:
                    tool_calls_log.append(call)
                async def _exec(call):
                    if self.event_bus:
                        self.event_bus.tool_start(call["name"], call.get("arguments", {}))
                    t0 = time.monotonic()
                    try:
                        r = await self.tools.execute(call["name"], call["arguments"])
                        from .context_optimization import OutputTruncator
                        result_text = json.dumps(r) if not isinstance(r, str) else r
                        result_text = OutputTruncator.truncate_tool_output(result_text)
                        if self.event_bus:
                            self.event_bus.tool_end(call["name"], result_text, True,
                                                    (time.monotonic() - t0) * 1000)
                        return result_text
                    except Exception as e:
                        if self.event_bus:
                            self.event_bus.tool_end(call["name"], str(e), False,
                                                    (time.monotonic() - t0) * 1000)
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
        if self.event_bus:
            self.event_bus.agent_finish(final_answer, iteration + 1)
            self.event_bus.context_update(self.context.get_total_tokens(),
                                          len(self.context.get_messages()),
                                          self.context.budget_tokens)
        return AgentResult(final_answer=final_answer, iterations=iteration + 1,
                           tool_calls=tool_calls_log, messages=self.context.get_messages_for_model())

    async def _stream_complete(self, provider, messages) -> tuple[str, list[dict[str, Any]]]:
        """Stream a completion, emitting deltas for live rendering."""
        parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        final_content = ""
        async for event in provider.stream(messages, self.tools.to_openai_tools(self.active_tools)):
            kind = event.get("type")
            if kind == "delta":
                parts.append(event.get("text", ""))
                if self.event_bus:
                    self.event_bus.llm_delta(event.get("text", ""))
            elif kind == "tool_call":
                tool_calls.append({"id": event.get("id"), "name": event.get("name", ""),
                                   "arguments": event.get("arguments", {})})
            elif kind == "done":
                final_content = event.get("content", "")
                tool_calls = event.get("tool_calls") or tool_calls
        return final_content or "".join(parts), tool_calls

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
