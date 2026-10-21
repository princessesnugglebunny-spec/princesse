"""Agent profiles loaded from YAML plus prompt templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AgentProfile:
    name: str
    title: str = ""
    description: str = ""
    context: str = ""
    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def load_profile(path: Path | str) -> AgentProfile:
    p = Path(path)
    data = yaml.safe_load(p.read_text()) if p.exists() else {}
    data = data or {}
    prompt_file = p.parent / "prompts" / "agent.system.main.md"
    system_prompt = prompt_file.read_text() if prompt_file.exists() else data.get("system_prompt", "")
    return AgentProfile(
        name=data.get("name", p.stem),
        title=data.get("title", ""),
        description=data.get("description", ""),
        context=data.get("context", ""),
        system_prompt=system_prompt,
        tools=data.get("tools", []),
        metadata=data.get("metadata", {}),
    )


def load_profiles(directory: Path | str) -> dict[str, AgentProfile]:
    d = Path(directory)
    profiles = {}
    if not d.exists():
        return profiles
    for yaml_file in d.glob("**/agent.yaml"):
        profile = load_profile(yaml_file)
        profiles[profile.name] = profile
    for yaml_file in d.glob("**/*.yaml"):
        if yaml_file.name == "agent.yaml":
            continue
        # allow loose profile files
        try:
            prof = load_profile(yaml_file)
            profiles.setdefault(prof.name, prof)
        except Exception:
            continue
    return profiles
