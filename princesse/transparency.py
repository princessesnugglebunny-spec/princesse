"""Real-time transparency bus: every decision, call, and tool action is observable."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .audit_log import redact, redact_mapping
from .logging_setup import get_logger, log_swallowed

logger = get_logger("transparency")


@dataclass
class Event:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    seq: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "ts": self.ts, "seq": self.seq, **self.data}


class EventBus:
    """Fan-out bus for runtime transparency events."""

    def __init__(self, history: bool = True):
        self._subscribers: list[Callable[[Event], None]] = []
        self._history: list[Event] = []
        self.keep_history = history
        self._seq = 0

    def subscribe(self, fn: Callable[[Event], None]) -> Callable[[Event], None]:
        self._subscribers.append(fn)
        return fn

    def unsubscribe(self, fn: Callable[[Event], None]):
        if fn in self._subscribers:
            self._subscribers.remove(fn)

    def emit(self, kind: str, **data: Any) -> Event:
        self._seq += 1
        event = Event(kind=kind, data=data, seq=self._seq)
        if self.keep_history:
            self._history.append(event)
        for fn in list(self._subscribers):
            try:
                fn(event)
            except Exception as e:
                log_swallowed(logger, "event subscriber failed", e, kind=event.kind, seq=event.seq)
        return event

    def history(self, kind: str | None = None) -> list[Event]:
        if kind is None:
            return list(self._history)
        return [e for e in self._history if e.kind == kind]

    def clear(self):
        self._history.clear()

    # convenience emitters -------------------------------------------------
    def agent_start(self, goal: str, **extra: Any):
        return self.emit("agent_start", goal=goal, **extra)

    def agent_finish(self, answer: str, iterations: int, **extra: Any):
        return self.emit("agent_finish", answer=answer, iterations=iterations, **extra)

    def llm_call(self, provider: str, model: str, messages: int, tools: int,
                 latency_ms: float, **extra: Any):
        return self.emit("llm_call", provider=provider, model=model, messages=messages,
                         tools=tools, latency_ms=round(latency_ms, 2), **extra)

    def llm_response(self, content: str, tool_calls: list[dict], **extra: Any):
        return self.emit("llm_response", content=content, tool_calls=tool_calls, **extra)

    def llm_delta(self, text: str, **extra: Any):
        return self.emit("llm_delta", text=text, **extra)

    def tool_start(self, name: str, args: dict, **extra: Any):
        return self.emit("tool_start", tool=name, args=args, **extra)

    def tool_end(self, name: str, result: Any, ok: bool, duration_ms: float, **extra: Any):
        return self.emit("tool_end", tool=name, result=result, ok=ok,
                         duration_ms=round(duration_ms, 2), **extra)

    def hook_match(self, hook_id: str, score: float, matched: list[str], **extra: Any):
        return self.emit("hook_match", hook=hook_id, score=score, matched=matched, **extra)

    def hook_action(self, hook_id: str, action: str, detail: Any = "", **extra: Any):
        return self.emit("hook_action", hook=hook_id, action=action, detail=detail, **extra)

    def memory_write(self, key: str, value: str, **extra: Any):
        return self.emit("memory_write", key=key, value=value, **extra)

    def context_update(self, tokens: int, messages: int, budget: int, **extra: Any):
        return self.emit("context_update", tokens=tokens, messages=messages, budget=budget, **extra)

    def iteration(self, index: int, **extra: Any):
        return self.emit("iteration", index=index, **extra)

    def note(self, message: str, **extra: Any):
        return self.emit("note", message=message, **extra)


class TranscriptWriter:
    """Writes a full-fidelity markdown transcript of a session."""

    def __init__(self, path: str = "transcript.md"):
        self.path = path
        self._lines: list[str] = []

    def attach(self, bus: EventBus) -> Callable[[Event], None]:
        def _on_event(event: Event) -> None:
            self._lines.append(self._render(event))
        bus.subscribe(_on_event)
        return _on_event

    def _render(self, event: Event) -> str:
        ts = time.strftime("%H:%M:%S", time.localtime(event.ts))
        d = event.data
        if event.kind == "agent_start":
            return f"\n## {ts} — goal\n\n{d.get('goal', '')}\n"
        if event.kind == "llm_call":
            return (f"\n### {ts} — LLM call\n\n"
                    f"- provider: `{d.get('provider')}`\n- model: `{d.get('model')}`\n"
                    f"- messages: {d.get('messages')} | tools offered: {d.get('tools')}\n"
                    f"- latency: {d.get('latency_ms')} ms\n")
        if event.kind == "llm_response":
            calls = d.get("tool_calls") or []
            body = redact(str(d.get("content", "")))
            text = f"\n#### {ts} — model output\n\n{body}\n"
            if calls:
                text += "\nRequested tools:\n\n"
                for c in calls:
                    text += f"- `{c.get('name')}` `{c.get('arguments')}`\n"
            return text
        if event.kind == "tool_start":
            args = redact_mapping(d.get("args") or {})
            return f"\n#### {ts} — tool `{d.get('tool')}`\n\n```json\n{args}\n```\n"
        if event.kind == "tool_end":
            status = "ok" if d.get("ok") else "FAILED"
            result = redact(str(d.get("result")))[:2000]
            return (f"\n#### {ts} — tool `{d.get('tool')}` {status} "
                    f"({d.get('duration_ms')} ms)\n\n```\n{result}\n```\n")
        if event.kind == "hook_match":
            return (f"\n#### {ts} — hook `{d.get('hook')}` matched "
                    f"(score {d.get('score')}, words {d.get('matched')})\n")
        if event.kind == "hook_action":
            return f"    - action `{d.get('action')}` → {d.get('detail')}\n"
        if event.kind == "memory_write":
            return f"\n#### {ts} — memory write `{d.get('key')}`\n\n{redact(str(d.get('value')))[:500]}\n"
        if event.kind == "context_update":
            return (f"\n#### {ts} — context: {d.get('tokens')}/{d.get('budget')} tokens "
                    f"across {d.get('messages')} messages\n")
        if event.kind == "iteration":
            return f"\n-- iteration {d.get('index')} --\n"
        if event.kind == "agent_finish":
            return f"\n## {ts} — final answer\n\n{d.get('answer', '')}\n"
        return f"\n- {ts} {event.kind}: {d}\n"

    def save(self, path: str | None = None) -> str:
        target = path or self.path
        with open(target, "w") as f:
            f.write("# Session transcript\n" + "".join(self._lines))
        return target
