"""Path sandbox, command policy, and skill verification."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PathEscapeError(Exception):
    """Raised when a path escapes its allowed root."""


def safe_path(path: str | Path, root: str | Path) -> Path:
    """Resolve `path` inside `root`, rejecting traversal and symlink escapes."""
    root_resolved = Path(root).expanduser().resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root_resolved / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as e:
        raise PathEscapeError(f"path escapes workspace: {path}") from e
    return resolved


DEFAULT_ALLOWED_COMMANDS = [
    "ls", "cat", "head", "tail", "grep", "find", "wc", "echo", "pwd", "git",
    "python3", "python", "pytest", "ruff", "mypy", "pyright", "node", "npm",
    "make", "diff", "tree", "stat", "which", "env",
]

DEFAULT_DENIED_PATTERNS = [
    r"\brm\s+-rf\s+/", r"\bsudo\b", r"\bmkfs\b", r"\bdd\s+if=", r":\(\)\{",
    r"\bcurl\b.*\|\s*(ba)?sh", r"\bwget\b.*\|\s*(ba)?sh", r"\bchmod\s+777\s+/",
]


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str = ""


class CommandPolicy:
    """Deny-by-default command allowlist with regex deny rules."""

    def __init__(self, allowed: list[str] | None = None, denied_patterns: list[str] | None = None):
        self.allowed = set(allowed if allowed is not None else DEFAULT_ALLOWED_COMMANDS)
        self.denied_patterns = [re.compile(p) for p in (denied_patterns if denied_patterns is not None else DEFAULT_DENIED_PATTERNS)]

    def check(self, command: str) -> PolicyDecision:
        for pattern in self.denied_patterns:
            if pattern.search(command):
                return PolicyDecision(False, f"denied by pattern: {pattern.pattern}")
        try:
            parts = command.split()
        except Exception:
            return PolicyDecision(False, "unparsable command")
        if not parts:
            return PolicyDecision(False, "empty command")
        program = Path(parts[0]).name
        if program not in self.allowed:
            return PolicyDecision(False, f"command not in allowlist: {program}")
        return PolicyDecision(True)

    def validate(self, command: str) -> str:
        decision = self.check(command)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        return command


@dataclass
class VerificationResult:
    ok: bool
    reason: str = ""
    sha256: str = ""
    signature_checked: bool = False


class SkillVerifier:
    """Verify downloaded skills by SHA-256 and optional cosign signature."""

    def __init__(self, expected_hashes: dict[str, str] | None = None,
                 signature: dict[str, str] | None = None,
                 use_cosign: bool = True):
        self.expected_hashes = expected_hashes or {}
        self.signatures = signature or {}
        self.use_cosign = use_cosign

    def hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def verify(self, path: Path | str, name: str | None = None) -> VerificationResult:
        p = Path(path)
        if not p.exists():
            return VerificationResult(False, "file missing")
        digest = self.hash_file(p)
        key = name or p.name
        expected = self.expected_hashes.get(key)
        if expected and expected.lower() != digest:
            return VerificationResult(False, "sha256 mismatch", digest)
        sig = self.signatures.get(key)
        signature_checked = False
        if sig and self.use_cosign and shutil.which("cosign"):
            ok = self._cosign_verify(p, sig)
            signature_checked = True
            if not ok:
                return VerificationResult(False, "cosign verification failed", digest, True)
        return VerificationResult(True, "ok", digest, signature_checked)

    def _cosign_verify(self, path: Path, signature: str) -> bool:
        cmd = ["cosign", "verify-blob", "--signature", signature, str(path)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return proc.returncode == 0
        except Exception:
            return False


class SandboxIsolator:
    """Execute tools in a restricted subprocess with resource limits."""

    def __init__(self, root: Path | str, timeout: int = 30, memory_mb: int = 512, network: bool = False):
        self.root = Path(root)
        self.timeout = timeout
        self.memory_mb = memory_mb
        self.network = network

    def _preexec(self):
        import resource

        def _limit():
            try:
                limit = self.memory_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
            except (ValueError, OSError):
                pass
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (self.timeout, self.timeout))
            except (ValueError, OSError):
                pass
            os_setsid = getattr(__import__("os"), "setsid", None)
            if os_setsid:
                try:
                    os_setsid()
                except OSError:
                    pass
        return _limit

    async def execute_tool(self, name: str, function, args: dict[str, Any], spec: dict[str, Any] | None = None) -> Any:
        """Run a tool callable in a subprocess worker with limits applied."""
        import asyncio
        payload = json.dumps({"name": name, "args": args})
        cmd = ["python3", "-c", _WORKER_SRC, payload, str(self.root)]
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(self.root),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            preexec_fn=self._preexec() if hasattr(asyncio.subprocess, "PIPE") else None,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError(f"sandboxed tool {name} timed out")
        if proc.returncode != 0:
            raise RuntimeError(err.decode(errors="replace")[:500])
        text = out.decode(errors="replace").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text


_WORKER_SRC = """
import json, sys, importlib, inspect
payload = json.loads(sys.argv[1])
root = sys.argv[2]
sys.path.insert(0, root)
name = payload["name"]
args = payload["args"]
mod = importlib.import_module(name)
fn = getattr(mod, "run")
result = fn(**args) if inspect.isfunction(fn) else fn(args)
if not isinstance(result, (str, int, float, bool, type(None), list, dict)):
    result = str(result)
print(json.dumps(result))
"""
