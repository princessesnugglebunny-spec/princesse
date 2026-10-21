"""Tool result cache for deterministic calls."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable


class ToolResultCache:
    def __init__(self, ttl: float = 300.0):
        self.ttl = ttl
        self._store: dict[str, tuple[float, Any]] = {}

    def key(self, name: str, args: dict[str, Any]) -> str:
        payload = json.dumps({"name": name, "args": args}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, name: str, args: dict[str, Any]) -> Any | None:
        k = self.key(name, args)
        if k in self._store:
            ts, val = self._store[k]
            if time.time() - ts < self.ttl:
                return val
            del self._store[k]
        return None

    def set(self, name: str, args: dict[str, Any], value: Any):
        self._store[self.key(name, args)] = (time.time(), value)

    def wrap(self, executor: Callable[[str, dict[str, Any]], Any]) -> Callable[[str, dict[str, Any]], Any]:
        async def wrapped(name: str, args: dict[str, Any]):
            cached = self.get(name, args)
            if cached is not None:
                return cached
            val = await executor(name, args)
            self.set(name, args, val)
            return val
        return wrapped

    def clear(self):
        self._store.clear()
