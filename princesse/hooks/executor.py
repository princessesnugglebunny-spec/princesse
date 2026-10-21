"""Hook action executor: preload tools/skills, inject context, switch profiles, run background work."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from .matching import HookMatch

@dataclass
class HookOutcome:
    applied: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class HookExecutor:
    """Applies hook actions to tools, skills, memory, profiles, and background tasks."""

    def __init__(self, tools=None, skills=None, memory=None, profiles: dict[str, Any] | None = None,
                 background: dict[str, Any] | None = None, advisor=None):
        self.tools = tools
        self.skills = skills
        self.memory = memory
        self.profiles = profiles or {}
        self.background = background or {}
        self.advisor = advisor
        self.last_outcome = HookOutcome()

    def apply(self, matches: list[HookMatch]) -> HookOutcome:
        outcome = HookOutcome()
        for match in matches:
            if match.hook is None:
                continue
            actions = match.hook.actions or {}
            for action, value in actions.items():
                try:
                    handler = getattr(self, f"_do_{action}", None)
                    if handler is None:
                        continue
                    detail = handler(value)
                    outcome.applied.append(f"{match.hook_id}:{action}")
                    if detail:
                        outcome.details[f"{match.hook_id}:{action}"] = detail
                except Exception as e:
                    outcome.errors.append(f"{match.hook_id}:{action}: {e}")
        self.last_outcome = outcome
        return outcome

    def _do_preload_tools(self, names: list[str]) -> list[str]:
        if self.tools is None:
            return []
        loaded = []
        for name in names or []:
            if self.tools.get(name):
                loaded.append(name)
        return loaded

    def _do_preload_skills(self, names: list[str]) -> list[str]:
        if self.skills is None:
            return []
        loaded = []
        for name in names or []:
            skill = self.skills.get(name)
            if skill:
                loaded.append(skill.name)
        return loaded

    def _do_inject_context(self, key: str) -> str:
        if self.memory is None:
            return ""
        entries = self.memory.search(key)
        return "\n".join(f"- {e.key}: {e.value}" for e in entries[:10])

    def _do_switch_profile(self, name: str) -> str:
        if name in self.profiles:
            return name
        return ""

    def _do_reuse_existing(self, task: str) -> str:
        if self.advisor is None:
            return ""
        return self.advisor.prompt_block(task)

    def _do_background(self, name: str) -> str:
        if name not in self.background:
            return ""
        fn = self.background[name]
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return ""
        if asyncio.iscoroutinefunction(fn):
            loop.create_task(fn())
        else:
            loop.create_task(asyncio.to_thread(fn))
        return name

    def prompt_injection(self, matches: list[HookMatch]) -> str:
        """Render matched hooks as extra system guidance."""
        if not matches:
            return ""
        lines = []
        for match in matches:
            if match.hook is None:
                continue
            skills = match.hook.actions.get("preload_skills") or []
            for skill_name in skills:
                skill = self.skills.get(skill_name) if self.skills else None
                if skill:
                    lines.append(f"[Skill: {skill.name}] {skill.content}")
            ctx = self._do_inject_context(match.hook.actions.get("inject_context", "")) if match.hook.actions.get("inject_context") else ""
            if ctx:
                lines.append(f"[Context: {match.hook.actions.get('inject_context')}]\n{ctx}")
            reuse = self._do_reuse_existing(match.hook.actions.get("reuse_existing", "")) if match.hook.actions.get("reuse_existing") else ""
            if reuse:
                lines.append(f"[Reuse existing code]\n{reuse}")
        return "\n\n".join(lines)
