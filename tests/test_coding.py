import asyncio
from princesse.coding_agent import CodingAgent

class FakeProvider2:
    def __init__(self, responses):
        self.responses = responses
        self.i = 0
    async def complete(self, messages, tools=None):
        r = self.responses[self.i % len(self.responses)]
        self.i += 1
        return r
    def parse_response(self, data):
        m = data["choices"][0]["message"]
        content = m.get("content") or ""
        calls = []
        import json
        for tc in m.get("tool_calls") or []:
            fn = tc["function"]
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except Exception:
                args = {}
            calls.append({"id": tc.get("id"), "name": fn["name"], "arguments": args})
        return content, calls

def test_coding_agent(tmp_path):
    (tmp_path/"test_ok.py").write_text("def test_x():\n    assert 1+1==2\n")
    provider = FakeProvider2([{"choices": [{"message": {"content": "done", "tool_calls": []}}]}])
    ca = CodingAgent(provider=provider, workspace=tmp_path)
    res = asyncio.run(ca.solve("nothing"))
    assert res.final == "done"
