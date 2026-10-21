"""Local retrieval over codebase and memory (TF-IDF + hashing vectors, no heavy deps)."""

from __future__ import annotations

import ast
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")
DEFAULT_EXTENSIONS = (".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".js", ".ts", ".go", ".rs", ".c", ".h", ".cpp", ".java", ".sh")


@dataclass
class Chunk:
    id: str
    path: str
    text: str
    kind: str = "text"
    symbol: str = ""
    start: int = 0
    end: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "path": self.path, "text": self.text, "kind": self.kind,
                "symbol": self.symbol, "start": self.start, "end": self.end,
                "metadata": self.metadata}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Chunk":
        return cls(id=data["id"], path=data["path"], text=data["text"], kind=data.get("kind", "text"),
                   symbol=data.get("symbol", ""), start=data.get("start", 0), end=data.get("end", 0),
                   metadata=data.get("metadata", {}))


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def split_identifiers(token: str) -> list[str]:
    parts = re.split(r"[_\-.]", token)
    out = []
    for p in parts:
        if not p:
            continue
        out.append(p.lower())
        if len(p) > 3 and p[0].isupper() and p[1:].islower():
            out.append(p.lower())
    return out


class Chunker:
    """AST-aware chunking for Python, line windows for everything else."""

    def chunk_file(self, path: Path, root: Path) -> list[Chunk]:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        if path.suffix == ".py":
            chunks = self._chunk_python(rel, source)
            if chunks:
                return chunks
        return self._chunk_window(rel, source)

    def _chunk_python(self, rel: str, source: str) -> list[Chunk]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        lines = source.splitlines()
        chunks: list[Chunk] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = getattr(node, "lineno", 1) - 1
                end = getattr(node, "end_lineno", start + 1)
                body = "\n".join(lines[start:end])
                name = node.name
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                doc = ast.get_docstring(node) or ""
                chunks.append(Chunk(id=f"{rel}:{name}:{start}", path=rel, text=body, kind=kind,
                                    symbol=name, start=start, end=end,
                                    metadata={"doc": doc[:500]}))
        return chunks

    def _chunk_window(self, rel: str, source: str, window: int = 60) -> list[Chunk]:
        lines = source.splitlines()
        chunks = []
        for i in range(0, len(lines), window):
            block = lines[i:i + window]
            chunks.append(Chunk(id=f"{rel}:{i}", path=rel, text="\n".join(block), kind="window",
                                start=i, end=i + len(block)))
        return chunks


class Vectorizer:
    """Hashing vectorizer with sublinear TF and L2 normalisation."""

    def __init__(self, dims: int = 512):
        self.dims = dims

    def vectorize(self, text: str) -> list[float]:
        counts = Counter(tokenize(text))
        for token in list(counts):
            counts.update(split_identifiers(token))
        vec = [0.0] * self.dims
        for token, count in counts.items():
            idx = hash(token) % self.dims
            vec[idx] += 1.0 + math.log(count)
        norm = math.sqrt(sum(v * v for v in vec))
        if norm:
            vec = [v / norm for v in vec]
        return vec

    @staticmethod
    def cosine(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b))


class Indexer:
    def __init__(self, root: Path | str = ".", dims: int = 512,
                 extensions: tuple[str, ...] = DEFAULT_EXTENSIONS):
        self.root = Path(root)
        self.dims = dims
        self.extensions = extensions
        self.chunker = Chunker()
        self.vectorizer = Vectorizer(dims)
        self.chunks: list[Chunk] = []
        self.vectors: list[list[float]] = []

    def scan(self) -> list[Chunk]:
        chunks: list[Chunk] = []
        if not self.root.exists():
            self.chunks, self.vectors = [], []
            return chunks
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.suffix not in self.extensions:
                continue
            if any(part.startswith(".") or part in {"__pycache__", "node_modules", "venv", ".venv"}
                   for part in path.parts):
                continue
            try:
                if path.stat().st_size > 2_000_000:
                    continue
            except OSError:
                continue
            chunks.extend(self.chunker.chunk_file(path, self.root))
        return chunks

    def build(self) -> int:
        chunks = self.scan()
        self.chunks = chunks
        self.vectors = [self.vectorizer.vectorize(c.text) for c in chunks]
        return len(chunks)

    def add_text(self, text: str, path: str = "memory", kind: str = "memory") -> int:
        chunk = Chunk(id=f"{path}:{len(self.chunks)}", path=path, text=text, kind=kind)
        self.chunks.append(chunk)
        self.vectors.append(self.vectorizer.vectorize(text))
        return len(self.chunks) - 1

    def search(self, query: str, k: int = 5, path_filter: str | None = None) -> list[tuple[Chunk, float]]:
        if not self.chunks:
            return []
        qvec = self.vectorizer.vectorize(query)
        scored = []
        for chunk, vec in zip(self.chunks, self.vectors):
            if path_filter and path_filter not in chunk.path:
                continue
            score = self.vectorizer.cosine(qvec, vec)
            if score > 0:
                scored.append((chunk, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def find_symbol(self, symbol: str) -> list[Chunk]:
        return [c for c in self.chunks if c.symbol == symbol]

    def save(self, path: Path | str):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"chunks": [c.to_dict() for c in self.chunks]}))

    def load(self, path: Path | str) -> int:
        p = Path(path)
        if not p.exists():
            return 0
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return 0
        self.chunks = [Chunk.from_dict(c) for c in data.get("chunks", [])]
        self.vectors = [self.vectorizer.vectorize(c.text) for c in self.chunks]
        return len(self.chunks)


class Retriever:
    """High-level retrieval facade used by hooks and the agent."""

    def __init__(self, indexer: Indexer | None = None, memory=None):
        self.indexer = indexer or Indexer()
        self.memory = memory

    def retrieve(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        results = []
        for chunk, score in self.indexer.search(query, k=k):
            results.append({"path": chunk.path, "symbol": chunk.symbol, "kind": chunk.kind,
                            "score": round(score, 4), "text": chunk.text[:2000]})
        return results

    def retrieve_code(self, symbol: str) -> list[dict[str, Any]]:
        return [{"path": c.path, "symbol": c.symbol, "kind": c.kind, "text": c.text[:2000]}
                for c in self.indexer.find_symbol(symbol)]

    def auto_index(self, root: Path | str | None = None) -> int:
        if root:
            self.indexer.root = Path(root)
        return self.indexer.build()

    def index_memory(self) -> int:
        if self.memory is None:
            return 0
        count = 0
        for entry in self.memory.all():
            self.indexer.add_text(f"{entry.key}\n{entry.value}", path=f"memory:{entry.key}", kind="memory")
            count += 1
        return count
