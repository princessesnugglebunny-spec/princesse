import asyncio
from princesse.tools import ToolRegistry, ToolParameter

def test_register_and_execute():
    reg = ToolRegistry()
    reg.reset()
    def add(a: int, b: int) -> int:
        return a + b
    entry = reg.register("add", add, "add two ints")
    assert entry.name == "add"
    res = asyncio.run(reg.execute("add", {"a": 2, "b": 3}))
    assert res == 5

def test_schema_export():
    reg = ToolRegistry()
    reg.reset()
    def f(x: str) -> str:
        return x
    reg.register("f", f, "identity")
    schemas = reg.to_openai_tools()
    assert any(s["function"]["name"] == "f" for s in schemas)

def test_validation():
    reg = ToolRegistry()
    reg.reset()
    def g(x: str) -> str:
        return x
    reg.register("g", g, "g", parameters=[ToolParameter(name="x", type="string", description="x", required=True)])
    try:
        asyncio.run(reg.execute("g", {}))
        assert False
    except ValueError:
        pass
