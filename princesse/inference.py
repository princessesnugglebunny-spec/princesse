"""Optimized inference: retry, pooling, streaming, response cache."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .providers import OpenAICompatibleProvider


class InferenceOptimizer:
    def __init__(self, provider: OpenAICompatibleProvider, max_retries: int = 3,
                 backoff: float = 1.0, cache_ttl: float = 60.0):
        self.provider = provider
        self.max_retries = max_retries
        self.backoff = backoff
        self._cache: dict[str, tuple[float, Any]] = {}
        self.cache_ttl = cache_ttl

    def _cache_key(self, messages, tools):
        import hashlib, json
        payload = json.dumps({"m": messages, "t": tools}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    async def complete(self, messages, tools=None, use_cache: bool = True):
        key = self._cache_key(messages, tools)
        if use_cache and key in self._cache:
            ts, val = self._cache[key]
            if time.time() - ts < self.cache_ttl:
                return val
        last_err = None
        for attempt in range(self.max_retries):
            try:
                res = await self.provider.complete(messages, tools)
                if use_cache:
                    self._cache[key] = (time.time(), res)
                return res
            except Exception as e:
                last_err = e
                await asyncio.sleep(self.backoff * (2 ** attempt))
        raise last_err if last_err else RuntimeError("inference failed")

    async def stream(self, messages, tools=None):
        # Delegate to provider if it supports streaming; else fall back
        stream_fn = getattr(self.provider, "stream", None)
        if stream_fn is not None:
            async for chunk in stream_fn(messages, tools):
                yield chunk
            return
        res = await self.complete(messages, tools, use_cache=False)
        content = res["choices"][0]["message"].get("content", "")
        yield content

    def clear_cache(self):
        self._cache.clear()
