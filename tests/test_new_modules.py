from pathlib import Path

import pytest

from princesse.audit_log import AuditLog, redact
from princesse.config import Config, load_config
from princesse.security import CommandPolicy, PathEscapeError, SkillVerifier, safe_path
from princesse.hooks import Hook, HookEngine, HookExecutor, TriggerSpec
from princesse.rag import Indexer, Retriever
from princesse.reuse import ReuseAdvisor, PatternLibrary, extract_signatures
from princesse.transparency import EventBus, TranscriptWriter


# ---------------------------------------------------------------- config
def test_config_defaults():
    cfg = Config()
    assert cfg.sandbox_enabled is True
    assert cfg.hooks_enabled is True
    assert isinstance(cfg.allowed_commands, list)


def test_config_from_dict_and_env(tmp_path, monkeypatch):
    cfg = Config.from_dict({"provider": "ollama", "max_iterations": 3,
                            "providers": {"ollama": {"base_url": "http://x/v1"}}})
    assert cfg.provider == "ollama"
    assert cfg.max_iterations == 3
    assert cfg.providers["ollama"].base_url == "http://x/v1"
    monkeypatch.setenv("PRINCESSE_PROVIDER", "openrouter")
    from princesse.config import _apply_env
    _apply_env(cfg)
    assert cfg.provider == "openrouter"


def test_load_config_from_yaml(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("provider: openrouter\nmax_iterations: 7\n")
    cfg = load_config(p)
    assert cfg.provider == "openrouter"
    assert cfg.max_iterations == 7


# ---------------------------------------------------------------- audit log
def test_audit_log_writes(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.log_tool_call("read_file", {"path": "a.py"}, "ok", 12.5, True)
    log.log_llm_call("m", "p", 10, 20, 33.0)
    recs = log.query()
    assert len(recs) == 2
    assert recs[0]["kind"] == "tool_call"
    assert recs[0]["correlation_id"] == log.correlation_id


def test_audit_redacts_secrets(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.log_tool_call("x", {"api_key": "sk-supersecret1234"}, "ok", 1.0, True)
    raw = (tmp_path / "audit.jsonl").read_text()
    assert "sk-supersecret1234" not in raw
    assert "REDACTED" in raw


def test_redact_bearer():
    assert "tok123456" not in redact("Authorization: Bearer tok123456")


# ---------------------------------------------------------------- security
def test_safe_path_blocks_escape(tmp_path):
    with pytest.raises(PathEscapeError):
        safe_path("../../etc/passwd", tmp_path)
    inside = safe_path("sub/file.txt", tmp_path)
    assert str(inside).startswith(str(tmp_path.resolve()))


def test_command_policy_allowlist():
    policy = CommandPolicy()
    assert policy.check("ls -la").allowed
    assert not policy.check("wget http://x").allowed
    assert not policy.check("rm -rf /").allowed
    assert not policy.check("sudo ls").allowed


def test_skill_verifier_hash(tmp_path):
    f = tmp_path / "s.md"
    f.write_text("---\nname: s\n---\nbody")
    digest = SkillVerifier().hash_file(f)
    ok = SkillVerifier(expected_hashes={"s.md": digest}).verify(f)
    assert ok.ok
    bad = SkillVerifier(expected_hashes={"s.md": "deadbeef"}).verify(f)
    assert not bad.ok


# ---------------------------------------------------------------- hooks
def _hook(words, order="loose", threshold=0.6, min_matches=1, proximity=60):
    return Hook(id="h", triggers=[TriggerSpec(words=words, order=order, threshold=threshold,
                                              min_matches=min_matches, proximity=proximity)],
                actions={"preload_tools": ["read_file"]})


def test_hook_loose_order():
    engine = HookEngine()
    engine.add(_hook(["debug", "error"]))
    assert engine.match("there is an error to debug")[0].hook_id == "h"
    assert engine.match("debug the error")[0].hook_id == "h"


def test_hook_strict_order_blocks_reversed():
    engine = HookEngine()
    engine.add(_hook(["debug", "error"], order="strict"))
    assert not engine.match("error debug")


def test_hook_fuzzy_match():
    engine = HookEngine()
    engine.add(_hook(["debug"], threshold=0.6))
    matches = engine.match("please debugg this")
    assert matches and matches[0].score > 0


def test_hook_rejects_garbage_fuzzy():
    engine = HookEngine()
    engine.add(_hook(["debug"], threshold=0.6))
    assert not engine.match("the pytest profiler ran")


def test_hook_synonyms():
    engine = HookEngine()
    engine.add(_hook(["error"]))
    assert engine.match("I hit an exception")


def test_hook_builtin_packs_load():
    engine = HookEngine([Path(__file__).parent.parent / "princesse" / "hooks" / "builtin"])
    ids = {h.id for h in engine.list_all()}
    assert "debug_session" in ids
    assert "code_review" in ids


def test_hook_executor_applies_actions(tmp_path):
    from princesse.tools import ToolRegistry
    from princesse.memory import MemoryStore
    reg = ToolRegistry()
    reg.reset()
    reg.register("read_file", lambda path: "x", "read")
    engine = HookEngine()
    engine.add(_hook(["debug"]))
    executor = HookExecutor(tools=reg, memory=MemoryStore(storage_path=tmp_path / "m.json"))
    outcome = executor.apply(engine.match("debug this"))
    assert any("preload_tools" in a for a in outcome.applied)


# ---------------------------------------------------------------- rag
def test_rag_index_and_search(tmp_path):
    (tmp_path / "a.py").write_text("def parse_config(path):\n    return {'path': path}\n")
    (tmp_path / "b.py").write_text("class Database:\n    def connect(self):\n        pass\n")
    indexer = Indexer(root=tmp_path)
    count = indexer.build()
    assert count >= 2
    results = indexer.search("parse config", k=3)
    assert results
    assert "a.py" in results[0][0].path


def test_rag_find_symbol(tmp_path):
    (tmp_path / "a.py").write_text("def unique_helper():\n    return 1\n")
    indexer = Indexer(root=tmp_path)
    indexer.build()
    found = indexer.find_symbol("unique_helper")
    assert found and found[0].path == "a.py"


def test_retriever_returns_dicts(tmp_path):
    (tmp_path / "a.py").write_text("def load_settings():\n    return {}\n")
    r = Retriever(indexer=Indexer(root=tmp_path))
    r.auto_index()
    out = r.retrieve("load settings")
    assert out and "path" in out[0]


# ---------------------------------------------------------------- reuse
def test_extract_signatures(tmp_path):
    (tmp_path / "m.py").write_text(
        "def helper(a, b):\n    '''doc'''\n    return a\n\nclass Thing:\n    def go(self):\n        pass\n")
    sigs = extract_signatures(tmp_path)
    entries = sigs["m.py"]
    kinds = {e["symbol"]: e["kind"] for e in entries}
    assert kinds["helper"] == "function"
    assert kinds["Thing"] == "class"


def test_reuse_advisor_suggests(tmp_path):
    (tmp_path / "m.py").write_text("def parse_configuration_file(path):\n    return path\n")
    advisor = ReuseAdvisor(root=tmp_path)
    advisor.build()
    cands = advisor.suggest("parse configuration file", k=3)
    assert cands
    assert cands[0].symbol == "parse_configuration_file"
    assert "parse_configuration_file" in advisor.prompt_block("parse configuration file")


def test_reuse_similar_symbols(tmp_path):
    (tmp_path / "m.py").write_text("def load_settings():\n    return {}\n")
    advisor = ReuseAdvisor(root=tmp_path)
    advisor.build()
    out = advisor.similar_symbols("load_settings")
    assert out and out[0]["symbol"] == "load_settings"


def test_pattern_library(tmp_path):
    pl = PatternLibrary()
    pl.record("create_tool", "princesse/tools.py")
    assert pl.suggest("create_tool") == ["princesse/tools.py"]
    pl.save(tmp_path / "patterns.json")
    pl2 = PatternLibrary().load(tmp_path / "patterns.json")
    assert pl2.suggest("create_tool")


# ---------------------------------------------------------------- transparency
def test_transcript_redacts_secrets(tmp_path):
    bus = EventBus()
    tw = TranscriptWriter(str(tmp_path / "t.md"))
    tw.attach(bus)
    bus.tool_start("login", {"api_key": "sk-leakme12345"})
    bus.tool_end("login", "token: sk-leakme12345", True, 1.0)
    text = Path(tw.save()).read_text()
    assert "sk-leakme12345" not in text


def test_event_bus_emits_and_records():
    bus = EventBus()
    seen = []
    bus.subscribe(seen.append)
    bus.agent_start("goal")
    bus.llm_call("p", "m", 1, 2, 3.0)
    bus.tool_start("read_file", {"path": "x"})
    bus.tool_end("read_file", "ok", True, 4.0)
    assert len(seen) == 4
    assert len(bus.history()) == 4
    assert bus.history("tool_start")[0].data["tool"] == "read_file"


def test_transcript_writer(tmp_path):
    bus = EventBus()
    tw = TranscriptWriter(str(tmp_path / "t.md"))
    tw.attach(bus)
    bus.agent_start("do the thing")
    bus.agent_finish("done", 1)
    out = tw.save()
    text = Path(out).read_text()
    assert "do the thing" in text
    assert "done" in text
