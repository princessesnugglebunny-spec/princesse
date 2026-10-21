"""Typed configuration with env > YAML > defaults layering."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_DIR = Path(os.getenv("PRINCESSE_HOME", Path.home() / ".princesse"))
DEFAULT_WORKSPACE = Path.cwd()


@dataclass
class ProviderConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    enabled: bool = True


@dataclass
class Config:
    workspace: Path = field(default_factory=lambda: DEFAULT_WORKSPACE)
    provider: str = "local"
    model: str = "auto"
    context_budget_tokens: int = 4000
    max_iterations: int = 10
    sandbox_enabled: bool = True
    allowed_commands: list[str] = field(default_factory=lambda: ["ls", "cat", "head", "tail", "grep", "find", "wc", "echo", "pwd", "git", "python3", "pytest", "ruff", "mypy", "pyright", "node", "npm", "make"])
    denied_patterns: list[str] = field(default_factory=lambda: [r"\brm\s+-rf\s+/", r"\bsudo\b", r"\bmkfs\b", r"\bdd\s+if=", r":\(\)\{", r"\bcurl\b.*\|\s*(ba)?sh", r"\bwget\b.*\|\s*(ba)?sh", r"\bchmod\s+777\s+/"])
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    hooks_enabled: bool = True
    hooks_dir: Path = field(default_factory=lambda: DEFAULT_CONFIG_DIR / "hooks")
    catalogue_url: str = "https://models.dev/api.json"
    catalogue_ttl_hours: int = 24
    auto_install: bool = True
    auto_install_lsp: bool = True
    auto_install_mcp: bool = True
    mcp_servers: list[str] = field(default_factory=list)
    rag_enabled: bool = True
    rag_max_chunks: int = 20000
    audit_log_path: Path = field(default_factory=lambda: DEFAULT_CONFIG_DIR / "audit.jsonl")
    boost_small_models: bool = True
    debug: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(v, Path):
                v = str(v)
            elif isinstance(v, ProviderConfig):
                v = {"base_url": v.base_url, "model": v.model, "enabled": v.enabled}
            elif isinstance(v, dict):
                v = {k: (vv if not isinstance(vv, ProviderConfig) else vv.model) for k, vv in v.items()}
            out[f.name] = v
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        cfg = cls()
        known = {f.name: f for f in fields(cls)}
        for key, value in (data or {}).items():
            if key not in known:
                continue
            current = getattr(cfg, key)
            if key == "providers" and isinstance(value, dict):
                providers = {}
                for name, pv in value.items():
                    if isinstance(pv, dict):
                        providers[name] = ProviderConfig(
                            base_url=pv.get("base_url", ""),
                            api_key=pv.get("api_key", ""),
                            model=pv.get("model", ""),
                            enabled=pv.get("enabled", True),
                        )
                    else:
                        providers[name] = ProviderConfig(model=str(pv))
                cfg.providers = providers
            elif isinstance(current, Path) and isinstance(value, str):
                setattr(cfg, key, Path(value).expanduser())
            elif isinstance(current, list) and isinstance(value, list):
                setattr(cfg, key, list(value))
            elif isinstance(current, bool) and isinstance(value, bool):
                setattr(cfg, key, value)
            elif isinstance(current, int) and isinstance(value, (int, float)) and not isinstance(value, bool):
                setattr(cfg, key, int(value))
            else:
                setattr(cfg, key, value)
        return cfg


def _read_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        text = path.read_text()
        if path.suffix == ".json":
            return json.loads(text)
        return yaml.safe_load(text) or {}
    except Exception:
        return {}


def load_config(config_path: Path | str | None = None) -> Config:
    """Load configuration: defaults -> user YAML -> project YAML -> env."""
    data: dict[str, Any] = {}
    if config_path:
        data.update(_read_config_file(Path(config_path)))
    else:
        data.update(_read_config_file(DEFAULT_CONFIG_DIR / "config.yaml"))
        data.update(_read_config_file(Path.cwd() / ".princesse" / "config.yaml"))
    cfg = Config.from_dict(data)
    _apply_env(cfg)
    return cfg


def _apply_env(cfg: Config) -> None:
    env_map = {
        "PRINCESSE_WORKSPACE": ("workspace", "path"),
        "PRINCESSE_PROVIDER": ("provider", "str"),
        "PRINCESSE_MODEL": ("model", "str"),
        "PRINCESSE_CONTEXT_BUDGET": ("context_budget_tokens", "int"),
        "PRINCESSE_MAX_ITERATIONS": ("max_iterations", "int"),
        "PRINCESSE_SANDBOX": ("sandbox_enabled", "bool"),
        "PRINCESSE_HOOKS_ENABLED": ("hooks_enabled", "bool"),
        "PRINCESSE_AUTO_INSTALL": ("auto_install", "bool"),
        "PRINCESSE_CATALOGUE_URL": ("catalogue_url", "str"),
        "PRINCESSE_BOOST": ("boost_small_models", "bool"),
        "PRINCESSE_DEBUG": ("debug", "bool"),
    }
    for env_key, (attr, kind) in env_map.items():
        raw = os.getenv(env_key)
        if raw is None:
            continue
        if kind == "path":
            setattr(cfg, attr, Path(raw).expanduser())
        elif kind == "int":
            try:
                setattr(cfg, attr, int(raw))
            except ValueError:
                pass
        elif kind == "bool":
            setattr(cfg, attr, raw.lower() in ("1", "true", "yes", "on"))
        else:
            setattr(cfg, attr, raw)
    mcp = os.getenv("PRINCESSE_MCP_SERVERS")
    if mcp:
        cfg.mcp_servers = [s.strip() for s in mcp.split(",") if s.strip()]
    for name, pc in cfg.providers.items():
        env_key = f"PRINCESSE_{name.upper()}_KEY"
        if not pc.api_key and os.getenv(env_key):
            pc.api_key = os.environ[env_key]
