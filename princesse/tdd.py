"""Test-driven coding helper: generate tests then code, iterate until green."""

from __future__ import annotations

from typing import Any

from .coding_agent import CodingAgent


class TDDCycle:
    def __init__(self, coding_agent: CodingAgent):
        self.ca = coding_agent

    async def run(self, spec: str, test_file: str = "test_solution.py",
                 impl_file: str = "solution.py", max_cycles: int = 5) -> dict[str, Any]:
        # Step 1: ask agent to write tests
        await self.ca.solve(f"Write pytest tests in {test_file} for: {spec}. Do not write implementation yet.")
        history = []
        for cycle in range(max_cycles):
            out = await self.ca.run_tests()
            history.append({"cycle": cycle, "output": out})
            if "failed" not in out.lower() and "error" not in out.lower():
                return {"success": True, "cycles": cycle + 1, "history": history}
            await self.ca.solve(f"Tests are failing. Fix implementation in {impl_file}. Test output:\n{out}")
        return {"success": False, "cycles": max_cycles, "history": history}
