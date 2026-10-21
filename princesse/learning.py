"""Learning loop: post-task review, memory nudges, auto skill creation."""

from __future__ import annotations

import hashlib
from typing import Any

from .memory import MemoryStore
from .skills import Skill, SkillRegistry


class LearningLoop:
    def __init__(self, memory: MemoryStore, skills: SkillRegistry):
        self.memory = memory
        self.skills = skills

    def review(self, goal: str, result: str, tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
        actions: list[str] = []
        # nudge memory
        nudges = self.memory.nudge(result)
        for n in nudges:
            self.memory.put(f"nudge:{len(self.memory.all())}", n, tags=["nudge", "auto"])
            actions.append(f"memory:{n}")
        # if many tool calls, create a skill summarizing the approach
        if len(tool_calls) >= 3:
            skill_name = "auto_" + hashlib.sha1(goal.encode()).hexdigest()[:8]
            content = f"Goal: {goal}\n\nApproach used {len(tool_calls)} tool calls.\nResult: {result[:500]}"
            skill = Skill(name=skill_name, description=f"Auto-created skill for: {goal[:80]}",
                          content=content, metadata={"auto": "true"})
            self.skills.register(skill, persist=True)
            actions.append(f"skill:{skill_name}")
        # record trajectory summary
        self.memory.put(f"trajectory:{hashlib.sha1(goal.encode()).hexdigest()[:12]}",
                        f"{goal} -> {result[:200]}", tags=["trajectory", "auto"])
        return {"actions": actions, "nudges": nudges}
