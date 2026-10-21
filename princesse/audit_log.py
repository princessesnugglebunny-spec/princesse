"""Append-only JSONL audit trail with correlation IDs and secret redaction."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

SECRET_PATTERNS = {
    "bearer": re.compile(r"(?i)\bbearer\s+([A-Za-z0-9._\-]{6,})"),
    "api_key": re.compile(
        r"(?i)(api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|authorization|credential)"
        r"\s*['\"]?\s*[:=]\s*['\"]?([^\s'\",}\]]{4,})"),
}

MAX_LOG_BYTES = 10 * 1024 * 1024
KEEP_ROTATIONS = 5


SENSITIVE_KEY_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|authorization|credential|token)")


def redact_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """Redact values whose key looks sensitive, plus any inline secrets in the rest."""
    out: dict[str, Any] = {}
    for key, value in (mapping or {}).items():
        if SENSITIVE_KEY_RE.search(str(key)):
            out[key] = "[REDACTED_API_KEY]"
        elif isinstance(value, str):
            out[key] = redact(value)
        else:
            out[key] = value
    return out


def redact(text: str) -> str:
    out = SECRET_PATTERNS["bearer"].sub("Bearer [REDACTED_BEARER]", text)
    out = SECRET_PATTERNS["api_key"].sub(
        lambda m: f"{m.group(1)}=[REDACTED_{'API_KEY' if 'key' in m.group(1).lower() else 'SECRET'}]",
        out)
    return out


class AuditLog:
    def __init__(self, path: Path | str = ".princesse/audit.jsonl", correlation_id: str | None = None):
        self.path = Path(path)
        self.correlation_id = correlation_id or uuid.uuid4().hex
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _write(self, record: dict[str, Any]) -> dict[str, Any]:
        record.setdefault("ts", time.time())
        record.setdefault("correlation_id", self.correlation_id)
        record["seq"] = self._next_seq()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._rotate_if_needed()
            with self.path.open("a") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except OSError:
            pass
        return record

    def _rotate_if_needed(self):
        try:
            if not self.path.exists() or self.path.stat().st_size < MAX_LOG_BYTES:
                return
            self.path.rename(self.path.with_suffix(self.path.suffix + ".1"))
            for i in range(KEEP_ROTATIONS - 1, 0, -1):
                old = self.path.with_suffix(self.path.suffix + f".{i}")
                new = self.path.with_suffix(self.path.suffix + f".{i + 1}")
                if old.exists():
                    old.rename(new)
        except OSError:
            pass

    def log_event(self, kind: str, **fields: Any) -> dict[str, Any]:
        return self._write({"kind": kind, **{k: redact(str(v)) if isinstance(v, str) else v for k, v in fields.items()}})

    def log_tool_call(self, name: str, args: dict[str, Any], result: Any, duration_ms: float, ok: bool) -> dict[str, Any]:
        return self._write({
            "kind": "tool_call",
            "tool": name,
            "args": redact_mapping(args or {}),
            "ok": ok,
            "duration_ms": round(duration_ms, 3),
            "result_preview": redact(str(result))[:500],
        })

    def log_llm_call(self, model: str, provider: str, prompt_tokens: int = 0,
                     completion_tokens: int = 0, latency_ms: float = 0.0, ok: bool = True) -> dict[str, Any]:
        return self._write({
            "kind": "llm_call",
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": round(latency_ms, 3),
            "ok": ok,
        })

    def log_install(self, kind: str, target: str, command: str, ok: bool) -> dict[str, Any]:
        return self._write({"kind": "install", "install_type": kind, "target": target,
                            "command": redact(command), "ok": ok})

    def query(self, kind: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if kind and rec.get("kind") != kind:
                    continue
                out.append(rec)
        return out[-limit:]

    def clear(self):
        try:
            if self.path.exists():
                os.unlink(self.path)
        except OSError:
            pass
