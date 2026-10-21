"""CLI-backed providers (kilo, alphacode) that need no API key."""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from typing import Any

from .registry import ProviderSpec


@dataclass
class CLIProvider:
    spec: ProviderSpec
    model: str = ""

    def available(self) -> bool:
        return bool(shutil.which(self.spec.cli_command[0]))

    async def complete(self, messages: list[dict[str, str]], tools: list[dict] | None = None) -> dict[str, Any]:
        """Run the CLI agent with the prompt and return an OpenAI-shaped response."""
        if not self.available():
            raise RuntimeError(f"{self.spec.cli_command[0]} is not installed")
        prompt = self._render_prompt(messages, tools)
        cmd = list(self.spec.cli_command) + ["--print", prompt]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=600)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"{self.spec.name} CLI timed out")
        text = out.decode(errors="replace").strip()
        if not text:
            raise RuntimeError(err.decode(errors="replace")[:300] or "empty output")
        return {"choices": [{"message": {"role": "assistant", "content": text, "tool_calls": []}}]}

    def _render_prompt(self, messages: list[dict[str, str]], tools: list[dict] | None) -> str:
        parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                parts.append(f"[System]\n{content}")
            elif role == "tool":
                parts.append(f"[Tool result]\n{content}")
            else:
                parts.append(f"[{role.capitalize()}]\n{content}")
        if tools:
            names = [t.get("function", {}).get("name") for t in tools]
            parts.append(f"[Available tools]\n{', '.join(n for n in names if n)}")
        return "\n\n".join(parts)

    def parse_response(self, data: dict[str, Any]) -> tuple[str, list[dict]]:
        message = data["choices"][0]["message"]
        return message.get("content", ""), []
