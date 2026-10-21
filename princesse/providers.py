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

    async def complete(self, messages, tools=None):
        import httpx
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
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
