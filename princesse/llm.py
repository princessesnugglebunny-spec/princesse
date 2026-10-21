"""LLM provider protocol and OpenAI-compatible implementation."""

from __future__ import annotations

from typing import Any, Protocol


class LLMProvider(Protocol):
    async def complete(self, messages: list[dict[str, str]], tools: list[dict] | None = None) -> dict[str, Any]:
        ...


class OpenAICompatibleProvider:
    def __init__(self, base_url: str = "http://localhost:8080/v1", api_key: str = "",
                 model: str = "default", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def complete(self, messages, tools=None, max_tokens: int | None = None, temperature: float | None = None):
        import httpx
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
        async with httpx.AsyncClient(timeout=self.timeout) as client:
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
        import httpx, json
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                        delta = obj["choices"][0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            yield delta["content"]
                    except json.JSONDecodeError:
                        continue
