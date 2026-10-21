"""Model catalogue: fetch, cache, refresh, and probe models."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CATALOGUE_URL = "https://models.dev/api.json"
DEFAULT_CACHE = Path.home() / ".princesse" / "catalogue.json"


@dataclass
class ModelInfo:
    id: str
    provider: str
    name: str = ""
    context: int = 0
    max_output: int = 0
    cost_input: float = 0.0
    cost_output: float = 0.0
    tool_call: bool = False
    reasoning: bool = False
    open_weights: bool = False
    family: str = ""
    release_date: str = ""

    @property
    def is_free(self) -> bool:
        return self.cost_input == 0 and self.cost_output == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "provider": self.provider, "name": self.name,
            "context": self.context, "max_output": self.max_output,
            "cost_input": self.cost_input, "cost_output": self.cost_output,
            "tool_call": self.tool_call, "reasoning": self.reasoning,
            "open_weights": self.open_weights, "family": self.family,
            "release_date": self.release_date, "is_free": self.is_free,
        }


@dataclass
class Catalogue:
    providers: dict[str, dict[str, Any]] = field(default_factory=dict)
    fetched_at: float = 0.0
    source: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any], source: str = "") -> "Catalogue":
        providers = payload.get("providers", payload) if isinstance(payload, dict) else {}
        return cls(providers=providers or {}, fetched_at=time.time(), source=source)

    def provider_names(self) -> list[str]:
        return list(self.providers.keys())

    def provider(self, name: str) -> dict[str, Any] | None:
        return self.providers.get(name)

    def base_url(self, name: str) -> str:
        p = self.providers.get(name) or {}
        return p.get("api", "") or ""

    def env_key(self, name: str) -> str:
        p = self.providers.get(name) or {}
        env = p.get("env") or []
        return env[0] if env else ""

    def models(self, provider: str) -> list[ModelInfo]:
        p = self.providers.get(provider) or {}
        out = []
        for mid, m in (p.get("models") or {}).items():
            limit = m.get("limit") or {}
            cost = m.get("cost") or {}
            out.append(ModelInfo(
                id=m.get("id", mid), provider=provider, name=m.get("name", mid),
                context=int(limit.get("context") or 0), max_output=int(limit.get("output") or 0),
                cost_input=float(cost.get("input") or 0.0), cost_output=float(cost.get("output") or 0.0),
                tool_call=bool(m.get("tool_call")), reasoning=bool(m.get("reasoning")),
                open_weights=bool(m.get("open_weights")), family=m.get("family", ""),
                release_date=m.get("release_date", ""),
            ))
        return out

    def all_models(self) -> list[ModelInfo]:
        out = []
        for name in self.providers:
            out.extend(self.models(name))
        return out

    def free_models(self, provider: str | None = None) -> list[ModelInfo]:
        models = self.models(provider) if provider else self.all_models()
        return [m for m in models if m.is_free]

    def find(self, query: str, provider: str | None = None) -> list[ModelInfo]:
        ql = query.lower()
        candidates = self.models(provider) if provider else self.all_models()
        scored = []
        for m in candidates:
            hay = f"{m.id} {m.name} {m.family}".lower()
            if ql in hay:
                score = 3 if ql == m.id.lower() else 2
                scored.append((score, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored]


class CatalogueManager:
    def __init__(self, url: str = DEFAULT_CATALOGUE_URL, cache_path: Path | str = DEFAULT_CACHE,
                 ttl_hours: float = 24.0):
        self.url = url
        self.cache_path = Path(cache_path)
        self.ttl_seconds = ttl_hours * 3600
        self.catalogue: Catalogue | None = None
        self._load_cache()

    def _load_cache(self):
        if not self.cache_path.exists():
            return
        try:
            data = json.loads(self.cache_path.read_text())
            payload = data.get("payload", data)
            self.catalogue = Catalogue.from_payload(payload, source=data.get("source", "cache"))
            self.catalogue.fetched_at = data.get("fetched_at", self.catalogue.fetched_at)
        except Exception:
            self.catalogue = None

    def _save_cache(self, payload: dict[str, Any], source: str):
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps({"fetched_at": time.time(), "source": source, "payload": payload}))
        except OSError:
            pass

    def is_stale(self) -> bool:
        if self.catalogue is None:
            return True
        return (time.time() - self.catalogue.fetched_at) > self.ttl_seconds

    async def refresh(self, force: bool = False) -> Catalogue | None:
        """Fetch a fresh catalogue. Non-fatal: returns the cached copy on failure."""
        if not force and not self.is_stale():
            return self.catalogue
        try:
            import httpx
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                resp = await client.get(self.url)
                resp.raise_for_status()
                payload = resp.json()
            self.catalogue = Catalogue.from_payload(payload, source=self.url)
            self._save_cache(payload, self.url)
        except Exception:
            if self.catalogue is None:
                self._load_cache()
        return self.catalogue

    def get(self) -> Catalogue | None:
        return self.catalogue

    async def test_model(self, base_url: str, model: str, api_key: str = "",
                         timeout: float = 30.0) -> dict[str, Any]:
        """Probe a model with a minimal completion to verify it works."""
        import httpx
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 4}
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers)
                latency = (time.monotonic() - started) * 1000
                if resp.status_code >= 400:
                    return {"model": model, "ok": False, "status": resp.status_code,
                            "reason": resp.text[:200], "latency_ms": round(latency, 2)}
                data = resp.json()
                content = data["choices"][0]["message"].get("content", "")
                return {"model": model, "ok": True, "status": resp.status_code,
                        "latency_ms": round(latency, 2), "sample": content[:80]}
        except Exception as e:
            return {"model": model, "ok": False, "reason": str(e),
                    "latency_ms": round((time.monotonic() - started) * 1000, 2)}
