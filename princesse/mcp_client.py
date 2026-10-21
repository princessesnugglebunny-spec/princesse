"""Minimal MCP client (stdio) for connecting to MCP servers."""

from __future__ import annotations

import json
import subprocess
import threading
from typing import Any

from .logging_setup import get_logger, log_swallowed

logger = get_logger("mcp_client")


class MCPClient:
    def __init__(self, command: list[str]):
        self.command = command
        self.process: subprocess.Popen | None = None
        self._id = 0
        self._lock = threading.Lock()

    def start(self) -> bool:
        try:
            self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, text=True, bufsize=1)
        except Exception:
            return False
        # initialize
        try:
            self._request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                         "clientInfo": {"name": "princesse", "version": "0.1"}})
            self._notify("notifications/initialized", {})
        except Exception as e:
            log_swallowed(logger, "mcp initialize failed", e, command=self.command[:3])
            return False
        return True

    def _next_id(self) -> int:
        with self._lock:
            self._id += 1
            return self._id

    def _request(self, method: str, params: dict[str, Any]) -> Any:
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("not started")
        rid = self._next_id()
        msg = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        self.process.stdin.write(json.dumps(msg) + "\n")
        self.process.stdin.flush()
        # read until matching id
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("eof")
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("id") == rid:
                if "error" in obj:
                    raise RuntimeError(str(obj["error"]))
                return obj.get("result")

    def _notify(self, method: str, params: dict[str, Any]):
        if self.process is None or self.process.stdin is None:
            return
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        self.process.stdin.write(json.dumps(msg) + "\n")
        self.process.stdin.flush()

    def list_tools(self) -> list[dict[str, Any]]:
        res = self._request("tools/list", {})
        return res.get("tools", []) if isinstance(res, dict) else []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return self._request("tools/call", {"name": name, "arguments": arguments})

    def stop(self):
        if self.process is not None:
            try:
                self.process.terminate()
            except Exception:
                pass
            self.process = None


class MCPRegistry:
    def __init__(self):
        self.clients: dict[str, MCPClient] = {}

    def connect(self, name: str, command: list[str]) -> bool:
        client = MCPClient(command)
        if client.start():
            self.clients[name] = client
            return True
        return False

    def disconnect(self, name: str):
        c = self.clients.pop(name, None)
        if c:
            c.stop()

    def all_tools(self) -> list[tuple[str, dict[str, Any]]]:
        out = []
        for name, c in self.clients.items():
            for t in c.list_tools():
                out.append((name, t))
        return out
