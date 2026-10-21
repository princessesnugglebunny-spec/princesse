"""Reuse advisor: find code that already exists before writing new code.

The agent should extend what is already in the repository instead of
reinventing helpers. This module turns the local index into a
"what already exists" lookup that can be injected into the prompt.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .rag import Indexer, tokenize

SIGNATURE_CACHE: dict[str, list[dict[str, Any]]] = {}


@dataclass
class Candidate:
    path: str
    symbol: str
    kind: str
    score: float
    signature: str = ""
    snippet: str = ""
    doc: str = ""
    why: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "symbol": self.symbol, "kind": self.kind,
                "score": round(self.score, 4), "signature": self.signature,
                "snippet": self.snippet[:600], "doc": self.doc[:300], "why": self.why}


def extract_signatures(root: Path | str) -> dict[str, list[dict[str, Any]]]:
    """Map file path -> list of {symbol, kind, signature, doc} for Python files."""
    root = Path(root)
    out: dict[str, list[dict[str, Any]]] = {}
    if not root.exists():
        return out
    for path in root.rglob("*.py"):
        if any(part.startswith(".") or part in {"__pycache__", "node_modules", "venv"}
               for part in path.parts):
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue
        entries = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = []
                for a in node.args.args:
                    args.append(a.arg)
                for a in node.args.kwonlyargs:
                    args.append(f"{a.arg}=")
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                entries.append({
                    "symbol": node.name, "kind": "function",
                    "signature": f"{prefix} {node.name}({', '.join(args)})",
                    "doc": (ast.get_docstring(node) or "")[:300],
                    "lineno": node.lineno,
                })
            elif isinstance(node, ast.ClassDef):
                methods = [n.name for n in node.body
                           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                entries.append({
                    "symbol": node.name, "kind": "class",
                    "signature": f"class {node.name}({', '.join(m for m in methods[:8])})",
                    "doc": (ast.get_docstring(node) or "")[:300],
                    "lineno": node.lineno,
                })
        if entries:
            try:
                out[str(path.relative_to(root))] = entries
            except ValueError:
                out[str(path)] = entries
    return out


@dataclass
class PatternLibrary:
    """Learned idioms of the repository, keyed by operation."""
    patterns: dict[str, list[str]] = field(default_factory=dict)

    def record(self, operation: str, example: str):
        self.patterns.setdefault(operation, [])
        if example not in self.patterns[operation]:
            self.patterns[operation].append(example)

    def suggest(self, operation: str, limit: int = 5) -> list[str]:
        return self.patterns.get(operation, [])[:limit]

    def to_dict(self) -> dict[str, list[str]]:
        return {k: v[:5] for k, v in self.patterns.items()}

    def save(self, path: Path | str):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2))

    def load(self, path: Path | str):
        p = Path(path)
        if not p.exists():
            return self
        try:
            data = json.loads(p.read_text())
            self.patterns = {k: list(v) for k, v in data.items()}
        except Exception:
            pass
        return self


class ReuseAdvisor:
    """Suggest existing code to reuse instead of writing new code."""

    STOPWORDS = {"the", "a", "an", "to", "of", "and", "or", "in", "on", "for", "with",
                 "is", "are", "be", "this", "that", "it", "as", "at", "by", "from"}

    def __init__(self, root: Path | str = ".", indexer: Indexer | None = None):
        self.root = Path(root)
        self.indexer = indexer or Indexer(root=self.root)
        self.signatures = extract_signatures(self.root)
        self.patterns = PatternLibrary()

    def build(self) -> int:
        return self.indexer.build()

    def _intent_terms(self, task: str) -> list[str]:
        words = [w for w in tokenize(task) if w not in self.STOPWORDS and len(w) > 2]
        return words

    def suggest(self, task: str, k: int = 5) -> list[Candidate]:
        """Rank existing symbols/chunks by how well they answer the task."""
        terms = self._intent_terms(task)
        if not terms:
            return []
        scored: dict[str, Candidate] = {}
        for path, entries in self.signatures.items():
            for entry in entries:
                hay = f"{entry['symbol']} {entry.get('doc', '')} {entry['kind']}".lower()
                hits = sum(1 for t in terms if t in hay)
                if not hits:
                    continue
                score = hits / len(terms)
                if entry["kind"] == "function":
                    score += 0.05
                key = f"{path}::{entry['symbol']}"
                if key not in scored or score > scored[key].score:
                    scored[key] = Candidate(path=path, symbol=entry["symbol"], kind=entry["kind"],
                                            score=score, signature=entry.get("signature", ""),
                                            doc=entry.get("doc", ""))
        for chunk, sim in self.indexer.search(task, k=k * 3):
            key = f"{chunk.path}::{chunk.symbol}" if chunk.symbol else chunk.id
            existing = scored.get(key)
            if existing is None:
                scored[key] = Candidate(path=chunk.path, symbol=chunk.symbol or "(block)",
                                        kind=chunk.kind, score=sim, snippet=chunk.text[:600])
            else:
                existing.score = max(existing.score, sim)
                existing.snippet = existing.snippet or chunk.text[:600]
        out = sorted(scored.values(), key=lambda c: c.score, reverse=True)[:k]
        for c in out:
            c.why = self._explain(c, terms)
        return out

    def _explain(self, candidate: Candidate, terms: list[str]) -> str:
        matched = [t for t in terms if t in f"{candidate.symbol} {candidate.doc}".lower()]
        if matched:
            return f"matches {', '.join(matched[:4])}"
        if candidate.snippet:
            return "similar implementation found in this repository"
        return "existing symbol in this repository"

    def similar_symbols(self, name: str, limit: int = 5) -> list[dict[str, Any]]:
        """Find existing symbols with a similar name (possible prior art)."""
        base = re.sub(r"[^a-z0-9]", "", name.lower())
        out = []
        for path, entries in self.signatures.items():
            for entry in entries:
                other = re.sub(r"[^a-z0-9]", "", entry["symbol"].lower())
                if other == base:
                    score = 1.0
                elif base in other or other in base:
                    score = 0.8
                elif set(base.split()) & set(other.split()):
                    score = 0.5
                else:
                    continue
                out.append({"path": path, "symbol": entry["symbol"], "kind": entry["kind"],
                            "score": score, "signature": entry.get("signature", "")})
        out.sort(key=lambda x: x["score"], reverse=True)
        return out[:limit]

    def prompt_block(self, task: str, k: int = 4) -> str:
        """Render reuse suggestions as a system-prompt block."""
        candidates = self.suggest(task, k=k)
        if not candidates:
            return ""
        lines = ["Existing code in this repository that you should prefer to reuse or extend "
                 "instead of writing from scratch:"]
        for c in candidates:
            lines.append(f"- {c.path}::{c.symbol} ({c.kind}) — {c.signature}")
            if c.doc:
                lines.append(f"  {c.doc.strip().splitlines()[0][:160]}")
            if c.snippet:
                first = c.snippet.strip().splitlines()[0][:160] if c.snippet.strip() else ""
                if first:
                    lines.append(f"  {first}")
        return "\n".join(lines)

    def operation_patterns(self, operation: str, limit: int = 5) -> list[str]:
        return self.patterns.suggest(operation, limit)

    def learn_from_edit(self, operation: str, file_path: str):
        self.patterns.record(operation, file_path)
