"""Auto skill discovery, download, and equipping."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from .skills import Skill, parse_skill, SkillRegistry


class SkillDownloader:
    def __init__(self, registry: SkillRegistry, index_url: str = ""):
        self.registry = registry
        self.index_url = index_url

    async def fetch_index(self) -> list[dict[str, Any]]:
        if not self.index_url:
            return []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(self.index_url)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return data
                return data.get("skills", [])
        except Exception:
            return []

    async def download_skill(self, url: str) -> Skill | None:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                skill = parse_skill(resp.text)
                if not skill.name:
                    return None
                return skill
        except Exception:
            return None

    async def sync(self) -> list[str]:
        equipped = []
        index = await self.fetch_index()
        for entry in index:
            url = entry.get("url") or entry.get("download_url")
            if not url:
                continue
            skill = await self.download_skill(url)
            if skill:
                self.registry.register(skill, persist=True)
                equipped.append(skill.name)
        return equipped

    def equip_from_directory(self, directory: Path | str) -> list[str]:
        d = Path(directory)
        equipped = []
        if not d.exists():
            return equipped
        for md in d.glob("*.md"):
            try:
                skill = parse_skill(md.read_text(), md)
                self.registry.register(skill)
                equipped.append(skill.name)
            except Exception:
                continue
        return equipped
