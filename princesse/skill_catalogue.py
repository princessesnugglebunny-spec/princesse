"""Skill catalogue: search installed skills and an optional remote index."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .skills import SkillRegistry

DEFAULT_CACHE = Path.home() / ".princesse" / "skill_catalogue.json"


@dataclass
class CatalogueSkill:
    name: str
    description: str = ""
    url: str = ""
    sha256: str = ""
    source: str = "local"
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "url": self.url,
                "sha256": self.sha256, "source": self.source, "tags": self.tags}


class SkillCatalogue:
    """Searchable index of locally installed skills plus an optional remote catalogue.

    The remote index is a simple JSON document: {"skills": [{"name", "description",
    "url", "sha256", "tags"}]}. No public registry is assumed; the URL is configured
    by the user so nothing is invented.
    """

    def __init__(self, registry: SkillRegistry | None = None, index_url: str = "",
                 cache_path: Path | str = DEFAULT_CACHE, ttl_hours: float = 12.0):
        self.registry = registry
        self.index_url = index_url
        self.cache_path = Path(cache_path)
        self.ttl_seconds = ttl_hours * 3600
        self._remote: list[CatalogueSkill] = []
        self._remote_time = 0.0
        self._load_cache()

    def _load_cache(self):
        if not self.cache_path.exists():
            return
        try:
            data = json.loads(self.cache_path.read_text())
            self._remote = [CatalogueSkill(**s) for s in data.get("skills", [])]
            self._remote_time = data.get("fetched_at", 0.0)
        except Exception:
            self._remote = []

    def _save_cache(self):
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps({
                "fetched_at": time.time(),
                "skills": [s.to_dict() for s in self._remote],
            }))
        except Exception:
            pass

    def local_skills(self) -> list[CatalogueSkill]:
        if self.registry is None:
            return []
        out = []
        for skill in self.registry.list_all():
            out.append(CatalogueSkill(name=skill.name, description=skill.description,
                                      source="local", tags=list(skill.tags)))
        return out

    async def refresh(self, force: bool = False) -> list[CatalogueSkill]:
        """Fetch the remote index (if configured). Non-fatal on failure."""
        if not self.index_url:
            return self._remote
        if not force and self._remote and (time.time() - self._remote_time) < self.ttl_seconds:
            return self._remote
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(self.index_url)
                resp.raise_for_status()
                data = resp.json()
            entries = data.get("skills", data if isinstance(data, list) else [])
            self._remote = [
                CatalogueSkill(name=str(e.get("name", "")), description=str(e.get("description", "")),
                               url=str(e.get("url", "")), sha256=str(e.get("sha256", "")),
                               source="remote", tags=[str(t) for t in (e.get("tags") or [])])
                for e in entries if e.get("name")
            ]
            self._remote_time = time.time()
            self._save_cache()
        except Exception:
            pass
        return self._remote

    async def search(self, query: str = "", limit: int = 20) -> list[CatalogueSkill]:
        remote = await self.refresh()
        entries = self.local_skills() + list(remote)
        if not query:
            return entries[:limit]
        ql = query.lower()
        words = [w for w in ql.split() if w]
        scored = []
        for entry in entries:
            hay = f"{entry.name} {entry.description} {' '.join(entry.tags)}".lower()
            score = sum(1 for w in words if w in hay)
            if ql in hay:
                score += 2
            if score:
                scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]

    async def install(self, name: str) -> dict[str, Any]:
        """Install a remote skill into the local registry after verifying its hash."""
        remote = await self.refresh()
        entry = next((s for s in remote if s.name == name), None)
        if entry is None:
            return {"ok": False, "reason": "skill not found in catalogue"}
        if self.registry is None:
            return {"ok": False, "reason": "no skill registry attached"}
        if not entry.url:
            return {"ok": False, "reason": "catalogue entry has no download url"}
        from .skill_download import SkillDownloader
        downloader = SkillDownloader(self.registry, index_url="")
        skill = await downloader.download_skill(entry.url)
        if skill is None:
            return {"ok": False, "reason": "download failed"}
        if entry.sha256:
            from .security import SkillVerifier
            tmp = self.registry.directory / f".incoming-{skill.name}.md"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(skill.to_markdown())
            result = SkillVerifier(expected_hashes={skill.name: entry.sha256}).verify(tmp, skill.name)
            tmp.unlink(missing_ok=True)
            if not result.ok:
                return {"ok": False, "reason": result.reason}
        self.registry.register(skill, persist=True)
        return {"ok": True, "name": skill.name}
