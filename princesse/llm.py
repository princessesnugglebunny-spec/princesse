"""LLM provider protocol and OpenAI-compatible implementation."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol


class LLMProvider(Protocol):
    async def complete(self, messages: list[dict[str, str]], tools: list[dict] | None = None) -> dict[str, Any]:
        ...


class ConnectionPool:
    """Process-wide httpx client pool, keyed by event loop.

    Reusing one client keeps connections alive between calls, which removes
    the TLS handshake cost from every LLM round trip.
    """

    _clients: dict[int, Any] = {}

    @classmethod
    def get(cls) -> Any:
        import httpx
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        key = id(loop) if loop is not None else 0
        client = cls._clients.get(key)
        if client is None or getattr(client, "is_closed", False):
            client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
            cls._clients[key] = client
        return client

    @classmethod
    async def close_all(cls) -> None:
        for client in list(cls._clients.values()):
            try:
                await client.aclose()
            except Exception:
                continue
        cls._clients.clear()


class OpenAICompatibleProvider:
    def __init__(self, base_url: str = "http://localhost:8080/v1", api_key: str = "",
                 model: str = "default", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def complete(self, messages, tools=None, max_tokens: int | None = None, temperature: float | None = None):
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        client = ConnectionPool.get()
        resp = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def parse_response(self, data: dict[str, Any]) -> tuple[str, list[dict]]:
        choice = data["choices"][0]["message"]
        content = choice.get("content") or ""
        tool_calls = choice.get("tool_calls") or []
        calls = []
        for tc in tool_calls:
            fn = tc["function"]
            import json
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            calls.append({"id": tc.get("id"), "name": fn["name"], "arguments": args})
        return content, calls

    async def stream(self, messages, tools=None, max_tokens: int | None = None):
        """Yield structured streaming events.

        Events: {"type": "delta", "text": str}, {"type": "tool_call", "name", "arguments"},
        {"type": "done", "content", "tool_calls"}.
        """
        import json
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        client = ConnectionPool.get()
        content_parts: list[str] = []
        partial: dict[int, dict[str, Any]] = {}
        async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload,
                                headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = (obj.get("choices") or [{}])[0].get("delta", {}) or {}
                text = delta.get("content")
                if text:
                    content_parts.append(text)
                    yield {"type": "delta", "text": text}
                for tc in delta.get("tool_calls") or []:
                    index = tc.get("index", 0)
                    slot = partial.setdefault(index, {"id": None, "name": "", "arguments": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] = fn["name"]
                    if fn.get("arguments"):
                        slot["arguments"] += fn["arguments"]
        tool_calls = []
        for index in sorted(partial):
            slot = partial[index]
            try:
                args = json.loads(slot["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({"id": slot["id"], "name": slot["name"], "arguments": args})
        yield {"type": "done", "content": "".join(content_parts), "tool_calls": tool_calls}
