"""Advanced context/token optimization to reduce degradation and token usage."""

from __future__ import annotations

import hashlib
from typing import Any

from .context import ContextWindow


class ImportanceScorer:
    """Score messages by recency, relevance, and tool success."""

    @staticmethod
    def score(message: dict[str, str], query: str, index: int, total: int) -> float:
        content = message.get("content", "").lower()
        ql = set(query.lower().split())
        relevance = sum(1 for w in ql if w in content) / max(1, len(ql))
        recency = (index + 1) / max(1, total)
        role_bonus = 0.2 if message.get("role") == "system" else 0.0
        error_penalty = -0.3 if "error" in content else 0.0
        return relevance * 0.4 + recency * 0.3 + role_bonus + error_penalty


class SemanticDeduplicator:
    @staticmethod
    def dedup(messages: list[dict[str, str]], threshold: float = 0.9) -> list[dict[str, str]]:
        out = []
        seen_hashes = set()
        for m in messages:
            h = hashlib.sha256(m.get("content", "").encode()).hexdigest()
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            out.append(m)
        return out


class TokenBudgetAllocator:
    """Allocate token budget across sections."""

    def __init__(self, total_budget: int):
        self.total = total_budget

    def allocate(self, sections: dict[str, int]) -> dict[str, int]:
        # sections: name -> priority (higher = more tokens)
        total_priority = sum(sections.values()) or 1
        result = {}
        for name, prio in sections.items():
            result[name] = int(self.total * prio / total_priority)
        return result


class SlidingWindowCompressor:
    """Keep a sliding window but preserve entities and key facts."""

    @staticmethod
    def compress(window: ContextWindow, keep_last: int = 4, preserve_entities: bool = True) -> list[dict[str, str]]:
        msgs = window.get_messages_for_model()
        if len(msgs) <= keep_last:
            return msgs
        # always keep system + last keep_last
        system_msgs = [m for m in msgs if m.get("role") == "system"]
        tail = msgs[-keep_last:]
        # middle: extract key facts
        middle = msgs[len(system_msgs):-keep_last] if len(msgs) > keep_last else []
        facts = []
        if preserve_entities and middle:
            import re
            for m in middle:
                entities = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", m.get("content", ""))
                if entities:
                    facts.append(f"entities: {', '.join(set(entities))}")
        result = list(system_msgs)
        if facts:
            result.append({"role": "system", "content": "[Preserved facts]\n" + "\n".join(facts[:20])})
        result.extend(tail)
        return result


class OutputTruncator:
    @staticmethod
    def truncate_tool_output(text: str, max_chars: int = 2000, keep_head: int = 1000, keep_tail: int = 500) -> str:
        if len(text) <= max_chars:
            return text
        return text[:keep_head] + f"\n... [{len(text) - keep_head - keep_tail} chars truncated] ...\n" + text[-keep_tail:]


class AdaptiveMaxTokens:
    @staticmethod
    def for_task(task: str, base: int = 512) -> int:
        # longer tasks -> more tokens
        length = len(task.split())
        if length < 10:
            return base
        if length < 50:
            return base * 2
        return base * 4


class ConversationSummarizer:
    """Summarize conversation preserving decisions and tool results."""

    @staticmethod
    def summarize(messages: list[dict[str, str]], max_tokens: int = 500) -> str:
        # extract key decisions and tool outcomes
        facts = []
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "assistant" and len(content) > 50:
                facts.append(f"assistant: {content[:120]}")
            elif role == "tool":
                facts.append(f"tool: {content[:80]}")
        joined = "\n".join(facts)
        # rough truncate
        if len(joined) > max_tokens * 4:
            joined = joined[:max_tokens * 4] + "..."
        return joined
