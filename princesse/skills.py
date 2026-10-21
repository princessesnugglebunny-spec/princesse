"""Skills: markdown files with front-matter, agentskills.io-compatible."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Skill:
    name: str
    description: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None

    def to_markdown(self) -> str:
        fm = "---\n"
        fm += f"name: {self.name}\n"
        fm += f"description: {self.description}\n"
        for k, v in self.metadata.items():
            fm += f"{k}: {v}\n"
        fm += "---\n\n"
        return fm + self.content


def parse_skill(text: str, path: Path | None = None) -> Skill:
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if m:
        fm_text, body = m.group(1), m.group(2)
        meta = {}
        name = ""
        desc = ""
        for line in fm_text.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip()
                if k == "name":
                    name = v
                elif k == "description":
                    desc = v
                else:
                    meta[k] = v
        return Skill(name=name or (path.stem if path else "unnamed"), description=desc,
                     content=body.strip(), metadata=meta, path=path)
    return Skill(name=path.stem if path else "unnamed", content=text.strip(), path=path)


class SkillRegistry:
    def __init__(self, directory: Path | str = ".princesse/skills"):
        self.directory = Path(directory)
        self._skills: dict[str, Skill] = {}
        self.load_all()

    def load_all(self):
        self._skills.clear()
        if self.directory.exists():
            for md in self.directory.glob("**/*.md"):
                try:
                    skill = parse_skill(md.read_text(), md)
                    self._skills[skill.name] = skill
                except Exception:
                    continue

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def register(self, skill: Skill, persist: bool = False):
        self._skills[skill.name] = skill
        if persist:
            self.directory.mkdir(parents=True, exist_ok=True)
            target = self.directory / f"{skill.name}.md"
            target.write_text(skill.to_markdown())
            skill.path = target

    def list_all(self) -> list[Skill]:
        return list(self._skills.values())

    def search(self, query: str) -> list[Skill]:
        ql = query.lower()
        return [s for s in self._skills.values()
                if ql in s.name.lower() or ql in s.description.lower() or ql in s.content.lower()]
