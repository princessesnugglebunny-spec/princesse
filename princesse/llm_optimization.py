"""LLM call optimization: coalescing, early stopping, prefetch."""

from __future__ import annotations

import asyncio
from typing import Any


class RequestCoalescer:
    """Batch multiple small prompts into one call (best-effort)."""

    def __init__(self, provider, window_ms: float = 50.0):
        self.provider = provider
        self.window_ms = window_ms
        self._pending: list[tuple[list[dict], asyncio.Future]] = []
        self._task = None

    async def submit(self, messages: list[dict[str, str]]) -> Any:
        fut = asyncio.get_event_loop().create_future()
        self._pending.append((messages, fut))
        if self._task is None or self._task.done():
            self._task = asyncio.ensure_future(self._flush())
        return await fut

    async def _flush(self):
        await asyncio.sleep(self.window_ms / 1000.0)
        batch = self._pending
        self._pending = []
        # execute each separately (coalescing at transport level is provider-specific)
        for messages, fut in batch:
            try:
                res = await self.provider.complete(messages, None)
                fut.set_result(res)
            except Exception as e:
                fut.set_exception(e)


class EarlyStopper:
    """Stop iterating if answer confidence is high."""

    @staticmethod
    def should_stop(answer: str, min_length: int = 20) -> bool:
        if not answer or len(answer) < min_length:
            return False
        low = answer.lower()
        if "i don't know" in low or "uncertain" in low:
            return False
        return True


class SpeculativePrefetcher:
    """Prefetch likely tools based on keywords in the goal."""

    KEYWORD_TOOLS = {
        "file": ["read_file", "list_dir"],
        "code": ["run_python", "run_terminal"],
        "git": ["git_status", "git_diff"],
        "web": ["browser_open"],
    }

    @staticmethod
    def predict(goal: str) -> list[str]:
        gl = goal.lower()
        tools = []
        for kw, ts in SpeculativePrefetcher.KEYWORD_TOOLS.items():
            if kw in gl:
                tools.extend(ts)
        return list(dict.fromkeys(tools))
