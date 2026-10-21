from princesse.git_tools import git_status, git_branch
from princesse.tool_cache import ToolResultCache
from princesse.memory_consolidation import MemoryConsolidator
from princesse.memory import MemoryStore
from pathlib import Path

def test_tool_cache():
    c = ToolResultCache(ttl=10)
    c.set("f", {"x": 1}, 42)
    assert c.get("f", {"x": 1}) == 42
    assert c.get("f", {"x": 2}) is None

def test_memory_consolidation(tmp_path):
    store = MemoryStore(storage_path=tmp_path/"m.json")
    for i in range(5):
        store.put(f"k{i}", f"v{i}", tags=["t"])
    mc = MemoryConsolidator(store)
    r = mc.consolidate(max_entries=3)
    assert "removed" in r
    assert r["total"] <= 5

def test_git_status(tmp_path):
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    r = git_status(str(tmp_path))
    assert "returncode" in r
