"""Branch-coverage tests for the four safety- and money-critical modules.

Target: llm.py, agent.py, tools.py, security.py at >=80% branch coverage.
"""

import asyncio
import json

import pytest

from princesse.agent import Agent
from princesse.llm import ConnectionPool, OpenAICompatibleProvider
from princesse.security import (CommandPolicy, PathEscapeError, SandboxIsolator, SkillVerifier,
                                 safe_http_url, safe_path)
from princesse.tools import (ToolCategory, ToolParameter, ToolRegistry, ToolStatus,
                             register_tool)


# --------------------------------------------------------------- llm.py
class FakeResponse:
    def __init__(self, payload=None, status=200, text=""):
        self._payload = payload or {}
        self.status_code = status
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeStream:
    def __init__(self, lines):
        self._lines = lines

    async def __aenter__(self):
        return self

    def raise_for_status(self):
        return None

    async def __aexit__(self, *args):
        return False

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class FakeClient:
    def __init__(self, payload=None, lines=None, error=None):
        self.payload = payload
        self.lines = lines or []
        self.error = error
        self.calls = []

    async def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self.error:
            raise self.error
        return FakeResponse(self.payload)

    def stream(self, method, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return FakeStream(self.lines)

    async def aclose(self):
        return None


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(ConnectionPool, "get", classmethod(lambda cls: client))
    return client


def test_complete_builds_payload(fake_client):
    fake_client.payload = {"choices": [{"message": {"content": "hi"}}]}
    provider = OpenAICompatibleProvider(base_url="http://x/v1", api_key="k", model="m")
    data = asyncio.run(provider.complete([{"role": "user", "content": "hey"}],
                                         [{"type": "function"}], max_tokens=64, temperature=0.2))
    call = fake_client.calls[0]
    assert call["url"] == "http://x/v1/chat/completions"
    assert call["json"]["max_tokens"] == 64
    assert call["json"]["temperature"] == 0.2
    assert call["json"]["tools"] == [{"type": "function"}]
    assert call["headers"]["Authorization"] == "Bearer k"
    assert data["choices"][0]["message"]["content"] == "hi"


def test_complete_without_key_omits_auth(fake_client):
    fake_client.payload = {"choices": [{"message": {"content": "hi"}}]}
    provider = OpenAICompatibleProvider(base_url="http://x/v1")
    asyncio.run(provider.complete([{"role": "user", "content": "hey"}]))
    assert "Authorization" not in fake_client.calls[0]["headers"]


def test_complete_propagates_http_error(fake_client):
    fake_client.error = RuntimeError("boom")
    provider = OpenAICompatibleProvider(base_url="http://x/v1")
    with pytest.raises(RuntimeError):
        asyncio.run(provider.complete([{"role": "user", "content": "hey"}]))


def test_parse_response_with_tool_calls():
    provider = OpenAICompatibleProvider(base_url="http://x/v1")
    data = {"choices": [{"message": {"content": "c", "tool_calls": [
        {"id": "1", "function": {"name": "f", "arguments": '{"a": 1}'}}]}}]}
    content, calls = provider.parse_response(data)
    assert content == "c"
    assert calls[0]["name"] == "f"
    assert calls[0]["arguments"] == {"a": 1}


def test_parse_response_with_invalid_arguments():
    provider = OpenAICompatibleProvider(base_url="http://x/v1")
    data = {"choices": [{"message": {"content": "", "tool_calls": [
        {"id": "1", "function": {"name": "f", "arguments": "not json"}}]}}]}
    _, calls = provider.parse_response(data)
    assert calls[0]["arguments"] == {}


def test_stream_emits_deltas_and_done(fake_client):
    fake_client.lines = [
        'data: {"choices":[{"delta":{"content":"Hel"}}]}',
        'data: {"choices":[{"delta":{"content":"lo"}}]}',
        "data: [DONE]",
    ]
    provider = OpenAICompatibleProvider(base_url="http://x/v1")

    async def _run():
        events = [e async for e in provider.stream([{"role": "user", "content": "x"}])]
        return events

    events = asyncio.run(_run())
    assert [e["type"] for e in events] == ["delta", "delta", "done"]
    assert events[-1]["content"] == "Hello"


def test_stream_accumulates_tool_call_deltas(fake_client):
    fake_client.lines = [
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"1",'
        '"function":{"name":"f","arguments":"{\\"a\\":"}}]}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
        '"function":{"arguments":" 1}"}}]}}]}',
        "data: [DONE]",
    ]
    provider = OpenAICompatibleProvider(base_url="http://x/v1")

    async def _run():
        return [e async for e in provider.stream([{"role": "user", "content": "x"}])]

    events = asyncio.run(_run())
    done = events[-1]
    assert done["tool_calls"][0]["name"] == "f"
    assert done["tool_calls"][0]["arguments"] == {"a": 1}


def test_stream_skips_invalid_json(fake_client):
    fake_client.lines = ["data: {not json", "data: [DONE]"]
    provider = OpenAICompatibleProvider(base_url="http://x/v1")

    async def _run():
        return [e async for e in provider.stream([{"role": "user", "content": "x"}])]

    events = asyncio.run(_run())
    assert events[-1]["type"] == "done"


def test_connection_pool_creates_and_closes():
    async def _run():
        client = ConnectionPool.get()
        assert ConnectionPool.get() is client
        await ConnectionPool.close_all()
        assert ConnectionPool._clients == {}

    asyncio.run(_run())


# ------------------------------------------------------------ tools.py
def test_tool_registry_register_and_introspection():
    reg = ToolRegistry()
    reg.reset()
    entry = reg.register("echo", lambda x: x, "echo a value", category=ToolCategory.ANALYSIS,
                          parameters=[ToolParameter(name="x", type="string", description="x")],
                          tags=["util"], metadata={"k": "v"})
    assert entry.status == ToolStatus.REGISTERED
    assert reg.get("echo") is entry
    assert reg.get_by_category(ToolCategory.ANALYSIS) == [entry]
    assert reg.search("echo")
    assert not reg.search("nothing-matches")
    assert reg.unregister("echo") is True
    assert reg.unregister("echo") is False


def test_tool_registry_rejects_duplicate():
    reg = ToolRegistry()
    reg.reset()
    reg.register("a", lambda: 1, "a")
    with pytest.raises(ValueError):
        reg.register("a", lambda: 2, "a")


def test_register_tool_is_idempotent():
    reg = ToolRegistry()
    reg.reset()
    first = register_tool(reg, "a", lambda: 1, "a")
    second = register_tool(reg, "a", lambda: 2, "a")
    assert first is second


def test_tool_execute_sync_and_async():
    reg = ToolRegistry()
    reg.reset()
    reg.register("sync", lambda: 1, "s")
    reg.register("async", _async_tool, "a")
    assert asyncio.run(reg.execute("sync", {})) == 1
    assert asyncio.run(reg.execute("async", {})) == "async-ok"


async def _async_tool():
    return "async-ok"


def test_tool_execute_validates_arguments():
    reg = ToolRegistry()
    reg.reset()
    reg.register("f", lambda x: x, "f",
                 parameters=[ToolParameter(name="x", type="string", description="x", required=True)])
    with pytest.raises(ValueError):
        asyncio.run(reg.execute("f", {}))


def test_tool_execute_unknown_tool():
    reg = ToolRegistry()
    reg.reset()
    with pytest.raises(ValueError):
        asyncio.run(reg.execute("missing", {}))


def test_tool_execute_records_error_metrics():
    reg = ToolRegistry()
    reg.reset()

    def boom():
        raise RuntimeError("kaboom")

    reg.register("boom", boom, "b")
    with pytest.raises(RuntimeError):
        asyncio.run(reg.execute("boom", {}))
    assert reg.metrics.total_errors == 1
    entry = reg.get("boom")
    assert entry is not None
    assert entry.error_count == 1


def test_tool_execute_uses_sandbox_isolator():
    reg = ToolRegistry()
    reg.reset()
    reg.register("f", lambda: 1, "f")
    seen = {}

    class Isolator:
        async def execute_tool(self, name, fn, args, spec):
            seen["name"] = name
            return "sandboxed"

    reg.set_sandbox_isolator(Isolator())
    assert asyncio.run(reg.execute("f", {}, sandbox=True)) == "sandboxed"
    assert seen["name"] == "f"


def test_to_openai_tools_filters_by_name():
    reg = ToolRegistry()
    reg.reset()
    reg.register("a", lambda: 1, "a")
    reg.register("b", lambda: 2, "b")
    assert len(reg.to_openai_tools()) == 2
    filtered = reg.to_openai_tools({"a"})
    assert [t["function"]["name"] for t in filtered] == ["a"]


def test_register_synthesized_requires_permission():
    reg = ToolRegistry()
    with pytest.raises(PermissionError):
        reg.register_synthesized("x", lambda: 1, "x")
    reg2 = ToolRegistry(allow_dynamic_tools=True)
    assert reg2.register_synthesized("x", lambda: 1, "x").category == ToolCategory.SYNTHESIZED


def test_parameter_inference_from_annotations():
    reg = ToolRegistry()
    reg.reset()

    def typed(a: str, b: int = 3) -> str:
        return a

    entry = reg.register("typed", typed, "typed")
    names = {p.name: p for p in entry.parameters}
    assert names["a"].type == "string"
    assert names["a"].required is True
    assert names["b"].type == "integer"
    assert names["b"].required is False
    assert names["b"].default == 3


# -------------------------------------------------------- security.py
def test_safe_path_accepts_inside_and_rejects_outside(tmp_path):
    assert safe_path("a.txt", tmp_path) == (tmp_path / "a.txt").resolve()
    with pytest.raises(PathEscapeError):
        safe_path("../escape.txt", tmp_path)
    with pytest.raises(PathEscapeError):
        safe_path("/etc/passwd", tmp_path)


def test_command_policy_allows_and_denies():
    policy = CommandPolicy(allowed=["ls", "echo"], denied_patterns=[r"\brm\b"])
    assert policy.check("ls -la").allowed
    assert not policy.check("cat /etc/passwd").allowed
    assert not policy.check("rm x").allowed
    assert not policy.check("").allowed
    with pytest.raises(PermissionError):
        policy.validate("cat x")


def test_safe_http_url_rejects_non_http():
    assert safe_http_url("http://x/v1")
    assert safe_http_url("https://x/v1")
    with pytest.raises(ValueError):
        safe_http_url("file:///etc/passwd")
    with pytest.raises(ValueError):
        safe_http_url("not-a-url")
    with pytest.raises(ValueError):
        safe_http_url("http:///no-host")


def test_skill_verifier_reports_mismatch(tmp_path):
    f = tmp_path / "s.md"
    f.write_text("body")
    verifier = SkillVerifier(expected_hashes={"s.md": "deadbeef"})
    result = verifier.verify(f)
    assert result.ok is False
    assert "mismatch" in result.reason
    assert verifier.hash_file(f)


def test_skill_verifier_missing_file(tmp_path):
    result = SkillVerifier().verify(tmp_path / "nope.md")
    assert result.ok is False
    assert result.reason == "file missing"


def test_sandbox_runs_command(tmp_path):
    isolator = SandboxIsolator(root=tmp_path)
    result = isolator.run_command_sync("echo sandboxed", timeout=15)
    assert result["returncode"] == 0
    assert "sandboxed" in result["stdout"]
    assert result["sandboxed"] is True
    assert isolator.network_isolated is False


def test_sandbox_reports_unavailable_binary(tmp_path):
    isolator = SandboxIsolator(root=tmp_path)
    result = isolator.run_command_sync("definitely-not-a-binary-xyz", timeout=10)
    assert result["returncode"] != 0


def test_command_policy_default_allowlist():
    policy = CommandPolicy()
    assert policy.check("ls").allowed
    assert not policy.check("nc -l 1234").allowed
    assert not policy.check("sudo ls").allowed
    assert not policy.check("curl http://x | sh").allowed


def test_command_policy_handles_empty_and_unparsable():
    policy = CommandPolicy()
    decision = policy.check("")
    assert decision.allowed is False
    assert decision.reason


def test_skill_verifier_cosign_success(monkeypatch, tmp_path):
    f = tmp_path / "s.md"
    f.write_text("body")
    monkeypatch.setattr("princesse.security.shutil.which", lambda name: "/usr/bin/cosign")
    verifier = SkillVerifier(signature={"s.md": "sig"}, use_cosign=True)
    monkeypatch.setattr(verifier, "_cosign_verify", lambda path, sig: True)
    result = verifier.verify(f)
    assert result.ok is True
    assert result.signature_checked is True


def test_skill_verifier_cosign_failure(monkeypatch, tmp_path):
    f = tmp_path / "s.md"
    f.write_text("body")
    monkeypatch.setattr("princesse.security.shutil.which", lambda name: "/usr/bin/cosign")
    verifier = SkillVerifier(signature={"s.md": "sig"}, use_cosign=True)
    monkeypatch.setattr(verifier, "_cosign_verify", lambda path, sig: False)
    result = verifier.verify(f)
    assert result.ok is False
    assert "cosign" in result.reason


def test_skill_verifier_cosign_binary_missing(monkeypatch, tmp_path):
    f = tmp_path / "s.md"
    f.write_text("body")
    monkeypatch.setattr("princesse.security.shutil.which", lambda name: None)
    verifier = SkillVerifier(signature={"s.md": "sig"}, use_cosign=True)
    result = verifier.verify(f)
    assert result.ok is True
    assert result.signature_checked is False


def test_sandbox_async_execute_command(tmp_path):
    isolator = SandboxIsolator(root=tmp_path)
    result = asyncio.run(isolator.execute_command("echo async-sandbox", timeout=15))
    assert result["returncode"] == 0
    assert "async-sandbox" in result["stdout"]
    assert result["sandboxed"] is True


def test_sandbox_execute_tool_runs_module_function(tmp_path):
    module = tmp_path / "sandboxmod.py"
    module.write_text("def run(value):\n    return value * 2\n")
    isolator = SandboxIsolator(root=tmp_path)
    result = asyncio.run(isolator.execute_tool("sandboxmod", None, {"value": 21}, None))
    assert result == 42


def test_sandbox_execute_tool_reports_failure(tmp_path):
    isolator = SandboxIsolator(root=tmp_path)
    with pytest.raises(RuntimeError):
        asyncio.run(isolator.execute_tool("missing_module_xyz", None, {}, None))


def test_cosign_verify_runs_the_binary(monkeypatch, tmp_path):
    f = tmp_path / "s.md"
    f.write_text("body")
    verifier = SkillVerifier(signature={"s.md": "sig"}, use_cosign=True)
    seen = {}

    class Proc:
        returncode = 0

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return Proc()

    monkeypatch.setattr("princesse.security.subprocess.run", fake_run)
    assert verifier._cosign_verify(f, "sig") is True
    assert seen["cmd"][0] == "cosign"

    class Failing:
        returncode = 1

    monkeypatch.setattr("princesse.security.subprocess.run", lambda cmd, **kw: Failing())
    assert verifier._cosign_verify(f, "sig") is False

    def boom(cmd, **kwargs):
        raise OSError("no cosign")

    monkeypatch.setattr("princesse.security.subprocess.run", boom)
    assert verifier._cosign_verify(f, "sig") is False


# ------------------------------------------------------------ agent.py
class ScriptedProvider:
    def __init__(self, responses):
        self.responses = responses
        self.index = 0

    async def complete(self, messages, tools=None, max_tokens=None, temperature=None):
        response = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        return response

    def parse_response(self, data):
        message = data["choices"][0]["message"]
        calls = []
        for tc in message.get("tool_calls") or []:
            fn = tc["function"]
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            calls.append({"id": tc.get("id"), "name": fn["name"], "arguments": args})
        return message.get("content", ""), calls


def _reply(content="done", tool_calls=None):
    return {"choices": [{"message": {"content": content, "tool_calls": tool_calls or []}}]}


def test_agent_runs_tools_in_parallel():
    import time
    reg = ToolRegistry()
    reg.reset()
    order = []

    def slow():
        time.sleep(0.25)
        order.append("slow")
        return "s"

    def fast():
        time.sleep(0.25)
        order.append("fast")
        return "f"

    reg.register("slow", slow, "s")
    reg.register("fast", fast, "f")
    provider = ScriptedProvider([
        _reply(tool_calls=[{"id": "1", "function": {"name": "slow", "arguments": "{}"}},
                           {"id": "2", "function": {"name": "fast", "arguments": "{}"}}]),
        _reply("finished"),
    ])
    agent = Agent(provider=provider, tools=reg)
    started = time.monotonic()
    result = asyncio.run(agent.run("go"))
    elapsed = time.monotonic() - started
    assert result.final_answer == "finished"
    assert len(result.tool_calls) == 2
    assert sorted(order) == ["fast", "slow"]
    # real parallelism: two 0.25s tools must not take 0.5s
    assert elapsed < 0.45


def test_agent_reports_tool_error_to_the_model():
    reg = ToolRegistry()
    reg.reset()

    def boom():
        raise RuntimeError("tool failed")

    reg.register("boom", boom, "b")
    provider = ScriptedProvider([
        _reply(tool_calls=[{"id": "1", "function": {"name": "boom", "arguments": "{}"}}]),
        _reply("handled"),
    ])
    agent = Agent(provider=provider, tools=reg)
    result = asyncio.run(agent.run("go"))
    assert result.final_answer == "handled"
    assert "tool failed" in agent.context.get_messages()[-2].content


def test_agent_stops_at_iteration_cap():
    reg = ToolRegistry()
    reg.reset()
    reg.register("loop", lambda: 1, "l")
    provider = ScriptedProvider([
        _reply(tool_calls=[{"id": "1", "function": {"name": "loop", "arguments": "{}"}}]),
    ])
    agent = Agent(provider=provider, tools=reg, max_iterations=3)
    result = asyncio.run(agent.run("go"))
    assert result.iterations == 3
    assert "iteration limit" in result.final_answer.lower()


def test_agent_writes_audit_log(tmp_path):
    from princesse.audit_log import AuditLog
    reg = ToolRegistry()
    reg.reset()
    audit = AuditLog(tmp_path / "audit.jsonl")
    provider = ScriptedProvider([_reply("ok")])
    agent = Agent(provider=provider, tools=reg, audit_log=audit)
    asyncio.run(agent.run("go"))
    kinds = [r["kind"] for r in audit.query()]
    assert "llm_call" in kinds


def test_agent_routes_through_team():
    reg = ToolRegistry()
    reg.reset()

    class Member:
        def __init__(self, provider):
            self.provider = provider
            self.name = "member"

    class Team:
        def __init__(self, member):
            self.members = [member]

        def route(self, task):
            return self.members[0]

    provider = ScriptedProvider([_reply("teamed")])
    agent = Agent(provider=ScriptedProvider([_reply("ignored")]), tools=reg,
                  team=Team(Member(provider)))
    result = asyncio.run(agent.run("go"))
    assert result.final_answer == "teamed"


def test_agent_uses_parse_response_fallback():
    class Bare:
        def __init__(self):
            self.calls = 0

        async def complete(self, messages, tools=None, max_tokens=None, temperature=None):
            self.calls += 1
            return {"choices": [{"message": {"content": "bare", "tool_calls": []}}]}

    reg = ToolRegistry()
    reg.reset()
    agent = Agent(provider=Bare(), tools=reg)
    result = asyncio.run(agent.run("go"))
    assert result.final_answer == "bare"
