from princesse.codebase_explore import CodebaseExplorer, extract_symbols
from pathlib import Path

def test_extract(tmp_path):
    p = tmp_path/"m.py"
    p.write_text("class A:\n    pass\ndef f(x):\n    return x\n")
    syms = extract_symbols(p)
    names = [s["name"] for s in syms]
    assert "A" in names and "f" in names

def test_explore_populate(tmp_path):
    root = tmp_path/"proj"
    root.mkdir()
    (root/"a.py").write_text("def g(): pass\n")
    from princesse.memory import MemoryStore
    store = MemoryStore(storage_path=tmp_path/"mem.json")
    exp = CodebaseExplorer(root=root, memory=store)
    n = exp.populate_memory()
    assert n >= 1
    assert store.get("codebase:symbol_count") is not None
