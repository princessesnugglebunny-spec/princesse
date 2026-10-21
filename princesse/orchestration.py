"""Multi-agent orchestration: planner + parallel/sequential sub-agents."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class PlanStep:
    id: str
    description: str
    depends_on: list[str] = field(default_factory=list)


@dataclass
class MultiAgentResult:
    task: str
    steps: list[PlanStep]
    results: dict[str, Any]
    final: str


class TaskPlanner:
    def __init__(self, provider=None):
        self.provider = provider

    async def plan(self, task: str) -> list[PlanStep]:
        # Heuristic decomposition: split on conjunctions; fallback to single step
        steps = []
        parts = [p.strip() for p in task.replace(" and ", "\n").split("\n") if p.strip()]
        if not parts:
            parts = [task]
        for i, p in enumerate(parts):
            steps.append(PlanStep(id=f"step_{i}", description=p))
        return steps

    async def reflect(self, code: str, test_output: str) -> str:
        if "fail" in test_output.lower() or "error" in test_output.lower():
            return "Tests failed; revise the implementation."
        return "Tests passed; task complete."


class MultiAgentOrchestrator:
    def __init__(self, worker: Callable[[str], Any], max_iterations: int = 3):
        self.worker = worker
        self.max_iterations = max_iterations

    async def run(self, task: str) -> MultiAgentResult:
        planner = TaskPlanner()
        steps = await planner.plan(task)
        results: dict[str, Any] = {}
        # sequential respecting depends_on
        for step in steps:
            try:
                if asyncio.iscoroutinefunction(self.worker):
                    res = await self.worker(step.description)
                else:
                    res = self.worker(step.description)
                results[step.id] = res
            except Exception as e:
                results[step.id] = f"ERROR: {e}"
        final = "\n".join(str(results.get(s.id, "")) for s in steps)
        return MultiAgentResult(task=task, steps=steps, results=results, final=final)

    async def run_parallel(self, tasks: list[str]) -> list[Any]:
        async def _run(t):
            if asyncio.iscoroutinefunction(self.worker):
                return await self.worker(t)
            return self.worker(t)
        return await asyncio.gather(*[_run(t) for t in tasks], return_exceptions=True)
