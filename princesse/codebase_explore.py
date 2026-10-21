"""Auto initial codebase exploration: scan tree, extract symbols, populate memory."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from .memory import MemoryStore


def extract_symbols(path: Path) -> list[dict[str, Any]]:
    results = []
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (SyntaxError, OSError):
        return results
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            results.append({"kind": "function", "name": node.name, "file": str(path),
                           "lineno": node.lineno, "args": [a.arg for a in node.args.args]})
        elif isinstance(node, ast.ClassDef):
            results.append({"kind": "class", "name": node.name, "file": str(path), "lineno": node.lineno})
    return results


class CodebaseExplorer:
    def __init__(self, root: Path | str, memory: MemoryStore | None = None,
                 extensions: tuple[str, ...] = (".py",)):
        self.root = Path(root)
        self.memory = memory
        self.extensions = extensions

    def scan(self) -> list[dict[str, Any]]:
        symbols: list[dict[str, Any]] = []
        if not self.root.exists():
            return symbols
        for path in self.root.rglob("*"):
            if path.is_file() and path.suffix in self.extensions:
                if any(part.startswith(".") or part in {"__pycache__", "node_modules"} for part in path.parts):
                    continue
                symbols.extend(extract_symbols(path))
        return symbols

    def populate_memory(self, symbols: list[dict[str, Any]] | None = None) -> int:
        if symbols is None:
            symbols = self.scan()
        if self.memory is None:
            return len(symbols)
        # group by file
        by_file: dict[str, list[str]] = {}
        for s in symbols:
            by_file.setdefault(s["file"], []).append(f"{s['kind']}:{s['name']}")
        count = 0
        for fpath, names in by_file.items():
            self.memory.put(f"codebase:{fpath}", ", ".join(names[:50]), tags=["codebase", "auto"])
            count += 1
        self.memory.put("codebase:root", str(self.root), tags=["codebase", "auto"])
        self.memory.put("codebase:symbol_count", str(len(symbols)), tags=["codebase", "auto"])
        return len(symbols)
