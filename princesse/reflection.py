"""Self-reflection loop: critique and retry."""

from __future__ import annotations

from typing import Any

from .agent import Agent


class ReflectionLoop:
    def __init__(self, agent: Agent, max_reflections: int = 2):
        self.agent = agent
        self.max_reflections = max_reflections

    async def run(self, goal: str) -> Any:
        result = await self.agent.run(goal)
        for _ in range(self.max_reflections):
            critique_prompt = (f"Review this answer for correctness and completeness. "
                               f"Goal: {goal}\nAnswer: {result.final_answer}\n"
                               f"Respond with 'OK' if good, else describe what to fix.")
            # use agent's provider directly for critique
            try:
                data = await self.agent.provider.complete(
                    [{"role": "system", "content": "You are a strict critic."},
                     {"role": "user", "content": critique_prompt}],
                    None,
                )
                content = data["choices"][0]["message"].get("content", "")
            except Exception:
                break
            if content.strip().upper().startswith("OK"):
                break
            # retry with critique appended
            result = await self.agent.run(goal + "\n\nCritique to address: " + content)
        return result
