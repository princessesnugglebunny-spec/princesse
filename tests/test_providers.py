import asyncio
import json

from princesse.providers import (BUILTIN_PROVIDERS, ProviderRegistry, ProviderSpec, ModelTeam,
                                 CatalogueManager, Catalogue, ModelInfo, CLIProvider)
from princesse.mcp_catalogue import MCPCatalogue, parse_server
from princesse.skill_catalogue import SkillCatalogue
from princesse.skills import SkillRegistry


def test_builtin_providers_present():
    for name in ("opencode", "opencode-go", "openrouter", "nvidia", "poolside",
                 "ollama", "llamacpp", "kilo", "alphacode"):
        assert name in BUILTIN_PROVIDERS


def test_provider_registry_lists_and_health():
    reg = ProviderRegistry()
    names = {s.name for s in reg.list_all()}
    assert "openrouter" in names
    health = reg.health("does-not-exist")
    assert health["ok"] is False


def test_provider_resolve_reads_env(monkeypatch):
    reg = ProviderRegistry()
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    key, url = reg.resolve("openrouter")
    assert key == "or-test"
    assert url == "https://openrouter.ai/api/v1"


def test_catalogue_parse_and_free_filter():
    payload = {"providers": {"acme": {
        "id": "acme", "name": "Acme", "api": "https://api.acme/v1", "env": ["ACME_API_KEY"],
        "models": {
            "free-model": {"id": "free-model", "name": "Free", "limit": {"context": 8000, "output": 100},
                           "cost": {"input": 0, "output": 0}, "tool_call": True},
            "paid-model": {"id": "paid-model", "name": "Paid", "limit": {"context": 8000, "output": 100},
                           "cost": {"input": 1.0, "output": 2.0}},
        }}}}
    cat = Catalogue.from_payload(payload)
    assert cat.base_url("acme") == "https://api.acme/v1"
    assert cat.env_key("acme") == "ACME_API_KEY"
    models = cat.models("acme")
    assert len(models) == 2
    free = cat.free_models()
    assert [m.id for m in free] == ["free-model"]
    found = cat.find("free")
    assert found and found[0].id == "free-model"


def test_catalogue_manager_cache(tmp_path):
    payload = {"providers": {"a": {"id": "a", "api": "http://a/v1", "models": {}}}}
    cache = tmp_path / "cat.json"
    cache.write_text(json.dumps({"fetched_at": 0, "source": "test", "payload": payload}))
    manager = CatalogueManager(cache_path=cache, ttl_hours=1)
    loaded = manager.get()
    assert loaded is not None
    assert manager.is_stale() is True


def test_catalogue_free_model_helper():
    m = ModelInfo(id="x", provider="p", cost_input=0.0, cost_output=0.0)
    assert m.is_free
    m2 = ModelInfo(id="y", provider="p", cost_input=0.1)
    assert not m2.is_free


def test_team_routing_prefers_capability():
    team = ModelTeam()
    team.add("coder", object(), tags=["code"])
    team.add("cheap", object(), tags=["summarize", "cheap"])
    picked = team.route("implement this function in code")
    assert picked is not None
    assert picked.name == "coder"


def test_team_ensemble_majority():
    class P:
        def __init__(self, text):
            self.text = text
        async def complete(self, messages, tools=None):
            return {"choices": [{"message": {"content": self.text}}]}
        def parse_response(self, data):
            return data["choices"][0]["message"]["content"], []

    team = ModelTeam()
    team.add("a", P("same"), tags=["general"])
    team.add("b", P("same"), tags=["general"])
    team.add("c", P("other"), tags=["general"])
    result = asyncio.run(team.ensemble("q", n=3))
    assert result["answer"] == "same"
    assert result["agreement"] >= 0.66


def test_mcp_server_parse():
    entry = {"server": {"name": "acme/fs", "description": "d", "title": "FS", "version": "1.0.0",
                        "packages": [{"registryType": "npm", "identifier": "fs-mcp",
                                      "version": "1.2.3", "runtimeHint": "npx",
                                      "transport": {"type": "stdio"},
                                      "runtimeArguments": [{"value": "-y"}],
                                      "environmentVariables": [{"name": "TOKEN", "isRequired": True}]}],
                        "remotes": [{"type": "streamable-http", "url": "https://x/mcp"}]}}
    info = parse_server(entry)
    assert info.name == "acme/fs"
    assert info.installable
    pkg = info.packages[0]
    assert pkg.launch_command()[0] == "npx"
    assert "fs-mcp@1.2.3" in " ".join(pkg.launch_command())
    assert pkg.required_env() == ["TOKEN"]


def test_mcp_catalogue_cache_fallback(tmp_path):
    cache = tmp_path / "mcp.json"
    cache.write_text(json.dumps({"fetched_at": 0, "payload": {
        "servers": [{"server": {"name": "acme/offline", "description": "c"}}]}}))
    cat = MCPCatalogue(url="http://127.0.0.1:1/unreachable", cache_path=cache)
    results = asyncio.run(cat.search("offline"))
    assert results and results[0].name == "acme/offline"


def test_skill_catalogue_local_search(tmp_path):
    reg = SkillRegistry(directory=tmp_path / "skills")
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "a.md").write_text("---\nname: alpha\ndescription: does alpha things\n---\nbody")
    reg.load_all()
    cat = SkillCatalogue(registry=reg)
    results = asyncio.run(cat.search("alpha"))
    assert results and results[0].name == "alpha"


def test_cli_bridge_requires_binary():
    spec = ProviderSpec("fake", "", cli_command=["definitely-not-installed-xyz"])
    bridge = CLIProvider(spec=spec)
    assert bridge.available() is False
