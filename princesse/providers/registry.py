"""Provider specs, registry, and health checks."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderSpec:
    name: str
    base_url: str
    env_key: str = ""
    label: str = ""
    local: bool = False
    cli_command: list[str] = field(default_factory=list)
    free_without_key: bool = False
    notes: str = ""

    @property
    def display(self) -> str:
        return self.label or self.name

    def key_present(self) -> bool:
        if self.local or self.cli_command:
            return True
        return bool(self.env_key and os.getenv(self.env_key))


BUILTIN_PROVIDERS: dict[str, ProviderSpec] = {
    "opencode": ProviderSpec("opencode", "https://opencode.ai/zen/v1", "OPENCODE_API_KEY",
                             label="OpenCode Zen", notes="Curated free+paid models; free tier needs a key from opencode.ai/auth"),
    "opencode-go": ProviderSpec("opencode-go", "https://opencode.ai/zen/go/v1", "OPENCODE_API_KEY",
                                label="OpenCode Go", notes="Low-cost subscription plan endpoint"),
    "openrouter": ProviderSpec("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
                               label="OpenRouter", notes="Aggregates 390+ models; many free"),
    "nvidia": ProviderSpec("nvidia", "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY",
                            label="NVIDIA NIM", notes="build.nvidia.com keys; free tier available"),
    "poolside": ProviderSpec("poolside", "https://inference.poolside.ai/v1", "POOLSIDE_API_KEY",
                              label="Poolside", notes="Code-focused models"),
    "ollama": ProviderSpec("ollama", "http://localhost:11434/v1", "", label="Ollama (local)", local=True),
    "llamacpp": ProviderSpec("llamacpp", "http://127.0.0.1:8080/v1", "", label="llama.cpp (local)", local=True),
    "lmstudio": ProviderSpec("lmstudio", "http://127.0.0.1:1234/v1", "", label="LM Studio (local)", local=True),
    "kilo": ProviderSpec("kilo", "", "", label="Kilo CLI (free)", cli_command=["kilo"], free_without_key=True,
                         notes="Shells out to the Kilo CLI agent; no API key required"),
    "alphacode": ProviderSpec("alphacode", "", "", label="AlphaCode CLI (free)", cli_command=["alphacode"],
                              free_without_key=True, notes="Shells out to the AlphaCode CLI agent; built-in free model"),
}


class ProviderRegistry:
    def __init__(self, specs: dict[str, ProviderSpec] | None = None):
        self.specs: dict[str, ProviderSpec] = dict(specs or BUILTIN_PROVIDERS)

    def register(self, spec: ProviderSpec):
        self.specs[spec.name] = spec
        return spec

    def get(self, name: str) -> ProviderSpec | None:
        return self.specs.get(name)

    def list_all(self) -> list[ProviderSpec]:
        return list(self.specs.values())

    def available(self) -> list[ProviderSpec]:
        """Providers that can be used right now (key present, local, or CLI installed)."""
        out = []
        for spec in self.specs.values():
            if spec.cli_command:
                if shutil.which(spec.cli_command[0]):
                    out.append(spec)
                continue
            if spec.local:
                out.append(spec)
                continue
            if spec.key_present():
                out.append(spec)
        return out

    def resolve(self, name: str) -> tuple[str | None, str]:
        """Return (api_key, base_url) for a provider name."""
        spec = self.specs.get(name)
        if spec is None:
            return None, ""
        key = os.getenv(spec.env_key, "") if spec.env_key else ""
        return (key or None), spec.base_url

    def health(self, name: str, timeout: float = 3.0) -> dict[str, Any]:
        spec = self.specs.get(name)
        if spec is None:
            return {"provider": name, "ok": False, "reason": "unknown provider"}
        if spec.cli_command:
            found = shutil.which(spec.cli_command[0])
            return {"provider": name, "ok": bool(found), "reason": "cli found" if found else "cli not installed"}
        if not spec.base_url:
            return {"provider": name, "ok": False, "reason": "no base url"}
        import urllib.error
        import urllib.request
        req = urllib.request.Request(f"{spec.base_url.rstrip('/')}/models")
        key = os.getenv(spec.env_key, "") if spec.env_key else ""
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return {"provider": name, "ok": resp.status == 200, "status": resp.status}
        except urllib.error.HTTPError as e:
            return {"provider": name, "ok": False, "status": e.code, "reason": str(e)}
        except Exception as e:
            return {"provider": name, "ok": False, "reason": str(e)}
