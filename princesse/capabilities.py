"""Capability tools distilled from slutt's non-core sections (simplified real impls)."""

from __future__ import annotations

import ast
import re
import time
from pathlib import Path
from typing import Any

from .tools import ToolRegistry, ToolCategory, ToolParameter


def complexity_evaluate(file_path: str) -> dict[str, Any]:
    path = Path(file_path)
    source = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source)
    funcs = 0
    branches = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs += 1
        if isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
            branches += 1
    loc = len(source.splitlines())
    return {"file": str(path), "functions": funcs, "branches": branches,
            "loc": loc, "complexity_score": branches + funcs}


def coverage_collect(project_path: str = ".") -> dict[str, Any]:
    # Lightweight: count python files and test files
    root = Path(project_path)
    py_files = list(root.rglob("*.py"))
    test_files = [p for p in py_files if "test" in p.name]
    return {"project": str(root), "python_files": len(py_files),
            "test_files": len(test_files), "test_ratio": (len(test_files) / max(1, len(py_files)))}


def pii_redact(text: str) -> dict[str, Any]:
    patterns = {
        "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        "phone": r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    }
    redacted = text
    found = {}
    for name, pat in patterns.items():
        matches = re.findall(pat, redacted)
        if matches:
            found[name] = len(matches)
            redacted = re.sub(pat, f"[REDACTED_{name.upper()}]", redacted)
    return {"redacted_text": redacted, "findings": found}


def telemetry_log(level: str, component: str, message: str) -> dict[str, Any]:
    entry = {"level": level.upper(), "component": component, "message": message,
             "timestamp": time.time()}
    return entry


def canary_evaluate(baseline: float, candidate: float, threshold: float = 0.05) -> dict[str, Any]:
    delta = (candidate - baseline) / max(abs(baseline), 1e-9)
    promote = delta >= -threshold
    return {"baseline": baseline, "candidate": candidate, "delta": delta,
            "promote": promote, "threshold": threshold}


def release_tag(current_version: str, release_type: str = "patch") -> str:
    parts = current_version.split(".")
    while len(parts) < 3:
        parts.append("0")
    major, minor, patch = (int(x) for x in parts[:3])
    if release_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif release_type == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}"


def hot_swap_reload(module_name: str) -> dict[str, Any]:
    import importlib
    import sys
    try:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
        else:
            importlib.import_module(module_name)
        return {"module": module_name, "reloaded": True}
    except Exception as e:
        return {"module": module_name, "reloaded": False, "error": str(e)}


def knowledge_extract(file_path: str) -> dict[str, Any]:
    path = Path(file_path)
    source = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source)
    classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    funcs = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return {"file": str(path), "classes": classes, "functions": funcs, "imports": imports}


def register_capability_tools(registry: ToolRegistry | None = None) -> ToolRegistry:
    reg = registry or ToolRegistry.get_instance()
    reg.register("complexity_evaluate", complexity_evaluate,
                "Evaluate cyclomatic-ish complexity of a Python file",
                category=ToolCategory.ANALYSIS,
                parameters=[ToolParameter(name="file_path", type="string", description="Path to file")])
    reg.register("coverage_collect", coverage_collect,
                "Collect lightweight coverage stats for a project",
                category=ToolCategory.ANALYSIS,
                parameters=[ToolParameter(name="project_path", type="string", description="Project root", required=False, default=".")])
    reg.register("pii_redact", pii_redact,
                "Redact PII (email/phone/ssn) from text",
                category=ToolCategory.ANALYSIS,
                parameters=[ToolParameter(name="text", type="string", description="Input text")])
    reg.register("telemetry_log", telemetry_log,
                "Create a telemetry log entry",
                category=ToolCategory.SYSTEM,
                parameters=[ToolParameter(name="level", type="string", description="Level"),
                           ToolParameter(name="component", type="string", description="Component"),
                           ToolParameter(name="message", type="string", description="Message")])
    reg.register("canary_evaluate", canary_evaluate,
                "Evaluate canary promotion decision",
                category=ToolCategory.ANALYSIS,
                parameters=[ToolParameter(name="baseline", type="number", description="Baseline metric"),
                           ToolParameter(name="candidate", type="number", description="Candidate metric"),
                           ToolParameter(name="threshold", type="number", description="Threshold", required=False, default=0.05)])
    reg.register("release_tag", release_tag,
                "Compute next release version",
                category=ToolCategory.SYSTEM,
                parameters=[ToolParameter(name="current_version", type="string", description="Current version"),
                           ToolParameter(name="release_type", type="string", description="major/minor/patch", required=False, default="patch",
                                       enum=["major", "minor", "patch"])])
    reg.register("hot_swap_reload", hot_swap_reload,
                "Reload an imported module",
                category=ToolCategory.SYSTEM,
                parameters=[ToolParameter(name="module_name", type="string", description="Module name")])
    reg.register("knowledge_extract", knowledge_extract,
                "Extract classes/functions/imports from a Python file",
                category=ToolCategory.ANALYSIS,
                parameters=[ToolParameter(name="file_path", type="string", description="Path to file")])
    return reg
