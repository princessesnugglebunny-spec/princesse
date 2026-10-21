"""Relevance-based context pruning to reduce tokens."""

from __future__ import annotations

from .context import ContextWindow


class ContextPruner:
    @staticmethod
    def prune(window: ContextWindow, query: str, max_messages: int = 8) -> list[dict[str, str]]:
        msgs = window.get_messages_for_model()
        if len(msgs) <= max_messages:
            return msgs
        # keep system + messages containing query keywords
        ql = set(query.lower().split())
        scored = []
        for i, m in enumerate(msgs):
            content = m.get("content", "").lower()
            score = sum(1 for w in ql if w in content)
            scored.append((score, i, m))
        # always keep last few
        keep_idx = set(i for _, i, _ in sorted(scored, key=lambda x: x[0], reverse=True)[:max_messages - 3])
        for i in range(max(0, len(msgs) - 3), len(msgs)):
            keep_idx.add(i)
        # keep system messages
        for i, m in enumerate(msgs):
            if m.get("role") == "system":
                keep_idx.add(i)
        out = [msgs[i] for i in sorted(keep_idx)]
        return out[:max_messages]
