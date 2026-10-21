"""Live integration tests.

These hit real networks and (optionally) a real OpenAI-compatible server, so they are
skipped by default. Enable them with:

    PRINCESSE_RUN_NETWORK_TESTS=1 pytest -m network

Environment:
    PRINCESSE_LIVE_BASE_URL  base URL of an OpenAI-compatible server
                             (default http://127.0.0.1:8080/v1)
    PRINCESSE_LIVE_MODEL     model id to request (default: whatever the server reports)
    PRINCESSE_LIVE_API_KEY   bearer token, if the server needs one
    PRINCESSE_LIVE_GGUF      path to a local GGUF file for the probe test
"""

import os
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        os.getenv("PRINCESSE_RUN_NETWORK_TESTS", "").lower() not in ("1", "true", "yes"),
        reason="set PRINCESSE_RUN_NETWORK_TESTS=1 to run live tests",
    ),
]

BASE_URL = os.getenv("PRINCESSE_LIVE_BASE_URL", "http://127.0.0.1:8080/v1")
API_KEY = os.getenv("PRINCESSE_LIVE_API_KEY", "")
MODEL = os.getenv("PRINCESSE_LIVE_MODEL", "local-model")
GGUF = os.getenv("PRINCESSE_LIVE_GGUF", "")


def _provider():
    from princesse.llm import OpenAICompatibleProvider
    return OpenAICompatibleProvider(base_url=BASE_URL, api_key=API_KEY, model=MODEL)


def test_live_server_is_reachable():
    import httpx
    response = httpx.get(f"{BASE_URL.rstrip('/')}/models", timeout=15.0)
    assert response.status_code == 200
    assert isinstance(response.json(), dict)


def test_live_completion():
    import asyncio
    provider = _provider()
    data = asyncio.run(provider.complete(
        [{"role": "user", "content": "Reply with the single word: ok"}], max_tokens=16))
    content, calls = provider.parse_response(data)
    assert content.strip()
    assert calls == []


def test_live_streaming_completion():
    import asyncio
    provider = _provider()

    async def _run():
        return [event async for event in provider.stream(
            [{"role": "user", "content": "Count: 1 2 3"}], max_tokens=16)]

    events = asyncio.run(_run())
    assert events
    assert events[-1]["type"] == "done"
    assert events[-1]["content"].strip()


def test_live_agent_runs_a_tool():
    import asyncio
    from princesse.agent import Agent
    from princesse.tools import ToolRegistry

    reg = ToolRegistry()
    reg.reset()
    reg.register("add", lambda a, b: a + b, "add two integers")
    provider = _provider()
    agent = Agent(provider=provider, tools=reg, max_iterations=4)
    result = asyncio.run(agent.run("What is 2 plus 3? Use the add tool if it helps."))
    assert result.final_answer.strip()


def test_live_hf_download(tmp_path):
    import asyncio
    from princesse.hf_download import HFDownloader

    repo = os.getenv("PRINCESSE_LIVE_HF_REPO", "unsloth/Qwen2.5-0.5B-Instruct-GGUF")
    filename = os.getenv("PRINCESSE_LIVE_HF_FILE", "qwen2.5-0.5b-instruct-q4_k_m.gguf")
    downloader = HFDownloader(chunks=4)
    path = asyncio.run(downloader.download_parallel(repo, filename, tmp_path))
    assert path.exists()
    assert path.stat().st_size > 0
    # the merged file must match the remote size
    import httpx
    head = httpx.head(f"https://huggingface.co/{repo}/resolve/main/{filename}",
                      follow_redirects=True, timeout=30.0)
    assert path.stat().st_size == int(head.headers["content-length"])


def test_live_gguf_probe():
    if not GGUF or not Path(GGUF).exists():
        pytest.skip("set PRINCESSE_LIVE_GGUF to a local .gguf file")
    from princesse.models import probe_gguf
    meta = probe_gguf(GGUF)
    assert meta.architecture
    assert meta.kv_count >= 0


def test_live_catalogue_refresh():
    import asyncio
    from princesse.providers import CatalogueManager
    manager = CatalogueManager(cache_path=Path(os.environ.get("TMPDIR", "/tmp")) / "live_catalogue.json")
    catalogue = asyncio.run(manager.refresh(force=True))
    assert catalogue is not None
    assert catalogue.provider_names()
