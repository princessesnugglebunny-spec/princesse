import asyncio
from princesse.orchestration import MultiAgentOrchestrator

def test_orchestrator():
    async def worker(t):
        return t.upper()
    orch = MultiAgentOrchestrator(worker=worker)
    res = asyncio.run(orch.run("foo and bar"))
    assert "FOO" in res.final
    assert "BAR" in res.final
