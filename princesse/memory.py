"""File-backed memory store with keyword search and periodic nudges."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class MemoryEntry:
    key: str
    value: str
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    access_count: int = 0


class MemoryStore:
    def __init__(self, storage_path: Path | str = ".princesse/memory.json"):
        self.storage_path = Path(storage_path)
        self._entries: dict[str, MemoryEntry] = {}
        self._load()

    def _load(self):
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text())
                for item in data.get("entries", []):
                    e = MemoryEntry(**item)
                    self._entries[e.key] = e
            except (json.JSONDecodeError, TypeError):
                self._entries = {}

    def _save(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"entries": [asdict(e) for e in self._entries.values()]}
        self.storage_path.write_text(json.dumps(data, indent=2))

    def put(self, key: str, value: str, tags: list[str] | None = None) -> MemoryEntry:
        now = time.time()
        if key in self._entries:
            e = self._entries[key]
            e.value = value
            e.tags = tags or e.tags
            e.updated_at = now
        else:
            e = MemoryEntry(key=key, value=value, tags=tags or [], created_at=now, updated_at=now)
        self._entries[key] = e
        self._save()
        return e

    def get(self, key: str) -> MemoryEntry | None:
        e = self._entries.get(key)
        if e:
            e.access_count += 1
        return e

    def delete(self, key: str) -> bool:
        if key in self._entries:
            del self._entries[key]
            self._save()
            return True
        return False

    def search(self, query: str, tags: list[str] | None = None) -> list[MemoryEntry]:
        ql = query.lower()
        results = []
        for e in self._entries.values():
            if tags and not any(t in e.tags for t in tags):
                continue
            if ql in e.key.lower() or ql in e.value.lower() or any(ql in t.lower() for t in e.tags):
                results.append(e)
        return results

    def all(self) -> list[MemoryEntry]:
        return list(self._entries.values())

    def nudge(self, context: str) -> list[str]:
        """Periodic self-nudge: return candidate facts worth persisting."""
        suggestions = []
        if len(context) > 200:
            suggestions.append("Consider persisting a summary of the recent task outcome.")
        if "error" in context.lower():
            suggestions.append("An error occurred; persist the failure mode and fix.")
        return suggestions


class MemoryNudge:
    def __init__(self, store: MemoryStore):
        self.store = store

    def run(self, context: str) -> list[str]:
        return self.store.nudge(context)
