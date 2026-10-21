"""Dynamic prompt assembler: profile + memory + skills + context."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .memory import MemoryStore


class PromptAssembler:
    def __init__(self, base_prompt: str = ""):
        self.base_prompt = base_prompt
        self.sections: list[str] = []

    def add_section(self, title: str, content: str):
        if content.strip():
            self.sections.append(f"## {title}\n{content.strip()}")

    def add_profile(self, profile) -> None:
        if getattr(profile, "system_prompt", ""):
            self.add_section("Role", profile.system_prompt)
        if getattr(profile, "context", ""):
            self.add_section("Context", profile.context)

    def add_memory(self, store: MemoryStore, query: str = "") -> None:
        entries = store.search(query) if query else store.all()
        if entries:
            lines = "\n".join(f"- {e.key}: {e.value}" for e in entries[:20])
            self.add_section("Memory", lines)

    def add_skills(self, skills: list[dict[str, Any]]) -> None:
        if skills:
            lines = "\n".join(f"- {s.get('name')}: {s.get('description', '')}" for s in skills)
            self.add_section("Skills", lines)

    def assemble(self) -> str:
        parts = [self.base_prompt] if self.base_prompt else []
        parts.extend(self.sections)
        return "\n\n".join(parts)
