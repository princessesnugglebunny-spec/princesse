"""MCP server catalogue: search the official registry, install or connect servers."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0/servers"
DEFAULT_CACHE = Path.home() / ".princesse" / "mcp_catalogue.json"


@dataclass
class MCPPackage:
    registry_type: str = "npm"          # npm | pypi
    identifier: str = ""
    version: str = ""
    runtime_hint: str = ""              # npx | uvx
    transport: str = "stdio"
    runtime_arguments: list[str] = field(default_factory=list)
    environment_variables: list[dict] = field(default_factory=list)

    def launch_command(self) -> list[str]:
        if self.runtime_hint == "npx":
            return ["npx", "-y", f"{self.identifier}@{self.version}" if self.version else self.identifier,
                    *self.runtime_arguments]
        if self.runtime_hint == "uvx":
            return ["uvx", f"{self.identifier}=={self.version}" if self.version else self.identifier,
                    *self.runtime_arguments]
        if self.registry_type == "pypi":
            return ["uvx", self.identifier]
        return ["npx", "-y", self.identifier]

    def required_env(self) -> list[str]:
        return [e["name"] for e in self.environment_variables if e.get("isRequired")]


@dataclass
class MCPServerInfo:
    name: str
    description: str = ""
    title: str = ""
    version: str = ""
    packages: list[MCPPackage] = field(default_factory=list)
    remotes: list[dict] = field(default_factory=list)

    @property
    def installable(self) -> bool:
        return bool(self.packages)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "title": self.title, "description": self.description,
                "version": self.version, "installable": self.installable,
                "remotes": self.remotes}


def parse_server(entry: dict[str, Any]) -> MCPServerInfo:
    sv = entry.get("server", entry) or {}
    packages = []
    for pkg in sv.get("packages") or []:
        packages.append(MCPPackage(
            registry_type=pkg.get("registryType", "npm"),
            identifier=pkg.get("identifier", ""),
            version=pkg.get("version", ""),
            runtime_hint=pkg.get("runtimeHint", ""),
            transport=(pkg.get("transport") or {}).get("type", "stdio"),
            runtime_arguments=[a.get("value", "") for a in (pkg.get("runtimeArguments") or [])],
            environment_variables=pkg.get("environmentVariables") or [],
        ))
    return MCPServerInfo(
        name=sv.get("name", ""), description=sv.get("description", ""),
        title=sv.get("title", ""), version=sv.get("version", ""),
        packages=packages, remotes=sv.get("remotes") or [],
    )


class MCPCatalogue:
    """Searchable catalogue of MCP servers backed by the official registry."""

    def __init__(self, url: str = REGISTRY_URL, cache_path: Path | str = DEFAULT_CACHE,
                 ttl_hours: float = 12.0):
        self.url = url
        self.cache_path = Path(cache_path)
        self.ttl_seconds = ttl_hours * 3600
        self._cache: dict[str, Any] | None = None
        self._cache_time = 0.0
        self._load_cache()

    def _load_cache(self):
        if not self.cache_path.exists():
            return
        try:
            data = json.loads(self.cache_path.read_text())
            self._cache = data.get("payload")
            self._cache_time = data.get("fetched_at", 0.0)
        except Exception:
            self._cache = None

    def _save_cache(self, payload: dict[str, Any]):
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps({"fetched_at": time.time(), "payload": payload}))
        except Exception:
            pass

    async def search(self, query: str = "", limit: int = 25) -> list[MCPServerInfo]:
        """Search the registry. Falls back to the cached payload on failure."""
        payload = None
        try:
            import httpx
            params = {"limit": str(limit)}
            if query:
                params["search"] = query
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(self.url, params=params)
                resp.raise_for_status()
                payload = resp.json()
            self._save_cache(payload)
            self._cache = payload
            self._cache_time = time.time()
        except Exception:
            payload = self._cache
        if not payload:
            return []
        out = []
        seen = set()
        for entry in payload.get("servers", []):
            info = parse_server(entry)
            if not info.name or info.name in seen:
                continue
            seen.add(info.name)
            out.append(info)
        if query:
            ql = query.lower()
            filtered = [s for s in out
                        if ql in s.name.lower() or ql in s.description.lower() or ql in s.title.lower()]
            return filtered[:limit]
        return out[:limit]

    async def install(self, name: str) -> dict[str, Any]:
        """Fetch a server entry and return the command needed to launch it locally."""
        servers = await self.search(name, limit=20)
        match = next((s for s in servers if s.name == name), None)
        if match is None:
            match = next((s for s in servers if name.lower() in s.name.lower()), None)
        if match is None:
            return {"ok": False, "reason": "not found in registry"}
        if match.remotes:
            return {"ok": True, "mode": "remote", "server": match.to_dict(),
                    "url": match.remotes[0].get("url")}
        if not match.packages:
            return {"ok": False, "reason": "server has no local package or remote", "server": match.to_dict()}
        pkg = match.packages[0]
        return {"ok": True, "mode": "local", "server": match.to_dict(),
                "command": pkg.launch_command(), "required_env": pkg.required_env()}
