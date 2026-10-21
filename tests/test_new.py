import asyncio
from princesse.learning import LearningLoop
from princesse.memory import MemoryStore
from princesse.skills import SkillRegistry
from pathlib import Path
from princesse.delegation import DelegationManager

def test_learning_loop(tmp_path):
    store = MemoryStore(storage_path=tmp_path/"m.json")
    skills = SkillRegistry(directory=tmp_path/"skills")
    ll = LearningLoop(memory=store, skills=skills)
    res = ll.review("goal", "result text", [{"a":1},{"b":2},{"c":3}])
    assert "actions" in res
    assert any("skill:" in a for a in res["actions"])

def test_delegation():
    def factory():
        class P:
            async def complete(self, messages, tools=None):
                return {"choices": [{"message": {"content": "sub answer", "tool_calls": []}}]}
            def parse_response(self, data):
                m = data["choices"][0]["message"]
                return m.get("content",""), []
        return P()
    dm = DelegationManager(provider_factory=factory)
    r = asyncio.run(dm.spawn("do x"))
    assert r["final_answer"] == "sub answer"
