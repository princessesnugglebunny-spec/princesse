from princesse.memory import MemoryStore

def test_put_get_search(tmp_path):
    store = MemoryStore(storage_path=tmp_path/"m.json")
    store.put("k1", "hello world", tags=["a"])
    e1 = store.get("k1")
    assert e1 is not None
    assert e1.value == "hello world"
    res = store.search("hello")
    assert len(res) == 1
    assert store.delete("k1")
    assert store.get("k1") is None

def test_persistence(tmp_path):
    p = tmp_path/"m.json"
    s1 = MemoryStore(storage_path=p)
    s1.put("k", "v")
    s2 = MemoryStore(storage_path=p)
    e2 = s2.get("k")
    assert e2 is not None
    assert e2.value == "v"
