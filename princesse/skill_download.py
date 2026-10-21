"""Auto skill discovery, download, and equipping."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from .security import SkillVerifier
from .skills import Skill, parse_skill, SkillRegistry


class SkillDownloader:
    def __init__(self, registry: SkillRegistry, index_url: str = "", verifier: SkillVerifier | None = None):
        self.registry = registry
        self.index_url = index_url
        self.verifier = verifier or SkillVerifier()

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

    def verify_skill_file(self, path: str | Path, name: str | None = None):
        """Verify a downloaded skill file; returns VerificationResult."""
        return self.verifier.verify(Path(path), name)

    async def sync(self) -> list[str]:
        equipped = []
        index = await self.fetch_index()
        for entry in index:
            url = entry.get("url") or entry.get("download_url")
            if not url:
                continue
            skill = await self.download_skill(url)
            if not skill:
                continue
            expected_hash = entry.get("sha256")
            verifier = SkillVerifier(expected_hashes={skill.name: expected_hash} if expected_hash else {})
            tmp = self.registry.directory / f".incoming-{skill.name}.md"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(skill.to_markdown())
            result = verifier.verify(tmp, skill.name)
            tmp.unlink(missing_ok=True)
            if not result.ok:
                continue
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
