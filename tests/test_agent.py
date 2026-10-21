import asyncio
from princesse.agent import Agent
from princesse.tools import ToolRegistry

class FakeProvider:
    def __init__(self, responses):
        self.responses = responses
        self.i = 0
    async def complete(self, messages, tools=None):
        r = self.responses[self.i]
        self.i += 1
        return r
    def parse_response(self, data):
        choice = data["choices"][0]["message"]
        content = choice.get("content") or ""
        calls = []
        for tc in choice.get("tool_calls") or []:
            import json
            fn = tc["function"]
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except Exception:
                args = {}
            calls.append({"id": tc.get("id"), "name": fn["name"], "arguments": args})
        return content, calls

def test_agent_scopes_tools_after_hook():
    from princesse.hooks import Hook, HookEngine, HookExecutor, TriggerSpec
    reg = ToolRegistry()
    reg.reset()
    reg.register("read_file", lambda path: "x", "read")
    reg.register("other_tool", lambda: "y", "other")
    engine = HookEngine()
    engine.add(Hook(id="h", triggers=[TriggerSpec(words=["debug"])],
                     actions={"preload_tools": ["read_file"]}))
    executor = HookExecutor(tools=reg)

    class P:
        def __init__(self):
            self.seen = None

        async def complete(self, messages, tools=None):
            self.seen = tools
            return {"choices": [{"message": {"content": "ok", "tool_calls": []}}]}

        def parse_response(self, data):
            return data["choices"][0]["message"]["content"], []

    provider = P()
    agent = Agent(provider=provider, tools=reg, hook_engine=engine, hook_executor=executor)
    asyncio.run(agent.run("debug this", use_optimizations=False))
    assert provider.seen is not None
    assert [t["function"]["name"] for t in provider.seen] == ["read_file"]


def test_agent_final_answer():
    reg = ToolRegistry()
    reg.reset()
    provider = FakeProvider([{"choices": [{"message": {"content": "hello", "tool_calls": []}}]}, {"choices": [{"message": {"content": "hello", "tool_calls": []}}]}])
    agent = Agent(provider=provider, tools=reg, system_prompt="sys")
    res = asyncio.run(agent.run("hi", use_optimizations=False))
    assert res.final_answer == "hello"

def test_agent_tool_call():
    reg = ToolRegistry()
    reg.reset()
    def echo(msg: str) -> str:
        return msg.upper()
    reg.register("echo", echo, "echo")
    provider = FakeProvider([
        {"choices": [{"message": {"content": "", "tool_calls": [{"id": "1", "function": {"name": "echo", "arguments": '{"msg":"hi"}'}}]}}]},
        {"choices": [{"message": {"content": "done", "tool_calls": []}}]},
        {"choices": [{"message": {"content": "done", "tool_calls": []}}]},
    ])
    agent = Agent(provider=provider, tools=reg, system_prompt="sys")
    res = asyncio.run(agent.run("do it", use_optimizations=False))
    assert res.final_answer == "done"
    assert len(res.tool_calls) == 1
