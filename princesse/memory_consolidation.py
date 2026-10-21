"""Memory consolidation: merge/prune entries."""

from __future__ import annotations

from .memory import MemoryStore


class MemoryConsolidator:
    def __init__(self, store: MemoryStore):
        self.store = store

    def consolidate(self, max_entries: int = 100) -> dict[str, int]:
        entries = self.store.all()
        removed = 0
        # prune oldest low-access entries if over limit
        if len(entries) > max_entries:
            entries_sorted = sorted(entries, key=lambda e: (e.access_count, e.updated_at))
            to_remove = len(entries) - max_entries
            for e in entries_sorted[:to_remove]:
                if self.store.delete(e.key):
                    removed += 1
        # merge entries with identical tags into a summary entry
        merged = 0
        tags_seen: dict[str, list] = {}
        for e in self.store.all():
            key = ",".join(sorted(e.tags))
            tags_seen.setdefault(key, []).append(e)
        for tag_key, group in tags_seen.items():
            if len(group) >= 3 and tag_key:
                summary_key = f"consolidated:{tag_key}"
                summary_val = " | ".join(e.value[:80] for e in group[:5])
                self.store.put(summary_key, summary_val, tags=tag_key.split(",") + ["consolidated"])
                merged += 1
        return {"removed": removed, "merged_groups": merged, "total": len(self.store.all())}
