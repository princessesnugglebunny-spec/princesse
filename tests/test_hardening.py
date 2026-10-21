"""Tests for the hardened runtime: sandbox, dynamic-tool gate, streaming, logging."""

import asyncio
import json
import logging

import pytest

from princesse.execution import ExecutionContext, run_terminal, run_python
from princesse.security import SandboxIsolator
from princesse.tools import ToolRegistry
from princesse.tool_synthesis import ToolSynthesizer
from princesse.transparency import EventBus
from princesse.logging_setup import JsonFormatter, configure, get_logger


# ------------------------------------------------------------- sandbox
def test_run_terminal_is_sandboxed_by_default(tmp_path):
    ctx = ExecutionContext(root=tmp_path)
    result = run_terminal("echo hi", context=ctx)
    assert result["returncode"] == 0
    assert result.get("sandboxed") is True
    assert "hi" in result["stdout"]


def test_run_terminal_host_execution_opt_in(tmp_path):
    ctx = ExecutionContext(root=tmp_path, allow_host_execution=True)
    result = run_terminal("echo hi", context=ctx)
    assert result["returncode"] == 0
    assert "sandboxed" not in result


def test_sandbox_runs_in_the_workspace(tmp_path):
    ctx = ExecutionContext(root=tmp_path)
    result = run_terminal("pwd", context=ctx)
    assert str(tmp_path.resolve()) in result["stdout"]


def test_sandbox_env_is_scrubbed(tmp_path):
    isolator = SandboxIsolator(root=tmp_path)
    assert isolator.env["HOME"] == str(tmp_path.resolve())
    assert "AWS_SECRET_ACCESS_KEY" not in isolator.env


def test_sandbox_limits_memory(tmp_path):
    isolator = SandboxIsolator(root=tmp_path, memory_mb=2048)
    assert isolator.memory_mb == 2048
    result = isolator.run_command_sync("python3 -c \"print('ok')\"", timeout=20)
    assert result["returncode"] == 0
    assert "ok" in result["stdout"]


def test_run_python_sandboxed(tmp_path):
    ctx = ExecutionContext(root=tmp_path)
    result = run_python("print(2+3)", context=ctx)
    assert result["returncode"] == 0
    assert "5" in result["stdout"]


# ------------------------------------------------------- dynamic tools
def test_dynamic_tools_disabled_by_default():
    reg = ToolRegistry()
    reg.reset()
    synth = ToolSynthesizer(reg)
    with pytest.raises(PermissionError):
        synth.synthesize("my_tool", "def run():\n    return 1\n")


def test_dynamic_tools_enabled_with_restricted_builtins():
    reg = ToolRegistry(allow_dynamic_tools=True)
    synth = ToolSynthesizer(reg)
    func = synth.synthesize("adder", "def run(a, b):\n    return a + b\n")
    assert func(2, 3) == 5


def test_synthesized_tool_cannot_open_files():
    reg = ToolRegistry(allow_dynamic_tools=True)
    synth = ToolSynthesizer(reg)
    func = synth.synthesize("reader", "def run():\n    return open('/etc/passwd').read()\n")
    with pytest.raises(NameError):
        func()


def test_synthesized_tool_cannot_import():
    reg = ToolRegistry(allow_dynamic_tools=True)
    synth = ToolSynthesizer(reg)
    func = synth.synthesize("importer", "def run():\n    return __import__('os').listdir('/')\n")
    with pytest.raises(NameError):
        func()


# ------------------------------------------------------------ streaming
class StreamingProvider:
    def __init__(self, chunks, tool_calls=None):
        self.chunks = chunks
        self.tool_calls = tool_calls or []
        self.used_stream = False

    async def complete(self, messages, tools=None):
        return {"choices": [{"message": {"content": "".join(self.chunks), "tool_calls": []}}]}

    async def stream(self, messages, tools=None):
        self.used_stream = True
        for chunk in self.chunks:
            yield {"type": "delta", "text": chunk}
        yield {"type": "done", "content": "".join(self.chunks), "tool_calls": self.tool_calls}

    def parse_response(self, data):
        return data["choices"][0]["message"]["content"], []


def test_agent_streams_when_enabled():
    from princesse.agent import Agent
    reg = ToolRegistry()
    reg.reset()
    bus = EventBus()
    deltas = []
    bus.subscribe(lambda e: deltas.append(e.data["text"]) if e.kind == "llm_delta" else None)
    provider = StreamingProvider(["Hello ", "world"])
    agent = Agent(provider=provider, tools=reg, stream_enabled=True, event_bus=bus)
    result = asyncio.run(agent.run("hi", use_optimizations=False))
    assert provider.used_stream is True
    assert result.final_answer == "Hello world"
    assert "".join(deltas) == "Hello world"


def test_agent_non_streaming_path():
    from princesse.agent import Agent
    reg = ToolRegistry()
    reg.reset()
    provider = StreamingProvider(["Hello"])
    agent = Agent(provider=provider, tools=reg, stream_enabled=False)
    result = asyncio.run(agent.run("hi", use_optimizations=False))
    assert provider.used_stream is False
    assert result.final_answer == "Hello"


# ------------------------------------------------------------- logging
def test_json_formatter_emits_json():
    record = logging.LogRecord("princesse.test", logging.INFO, "f.py", 1, "hello", None, None)
    record.correlation_id = "abc123"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["correlation_id"] == "abc123"


def test_configure_is_idempotent():
    first = configure()
    second = configure()
    assert first is second


def test_get_logger_returns_child():
    logger = get_logger("unit")
    assert logger.name.endswith("unit")


# ---------------------------------------------------------- connection pool
def test_connection_pool_reuses_client():
    from princesse.llm import ConnectionPool

    async def _check():
        first = ConnectionPool.get()
        second = ConnectionPool.get()
        assert first is second
        await ConnectionPool.close_all()

    asyncio.run(_check())
