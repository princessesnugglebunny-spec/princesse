"""Rolling context window with hierarchical summarization."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_BUDGET_TOKENS = int(os.getenv("PRINCESSE_CONTEXT_BUDGET_TOKENS", "4000"))
DEFAULT_VERBATIM_TAIL = int(os.getenv("PRINCESSE_CONTEXT_VERBATIM_TAIL", "8"))


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class SummaryTier:
    IMMEDIATE = "immediate"
    RECENT = "recent"
    SESSION = "session"
    HISTORICAL = "historical"
    SEMANTIC = "semantic"


@dataclass
class Summary:
    id: str
    tier: str
    content: str
    source_tokens: int
    summary_tokens: int
    compression_ratio: float
    key_points: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextMessage:
    role: str
    content: str
    tokens: int = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.tokens == 0:
            self.tokens = estimate_tokens(self.content)


class HierarchicalSummarizer:
    def __init__(self, max_immediate: int = 5, max_recent: int = 20, max_session: int = 100):
        self.max_immediate = max_immediate
        self.max_recent = max_recent
        self.max_session = max_session
        self.immediate_summaries: list[Summary] = []
        self.recent_summaries: list[Summary] = []
        self.session_summaries: list[Summary] = []
        self.historical_summaries: list[Summary] = []
        self.semantic_summaries: list[Summary] = []

    def add_interaction(self, user_msg: str, assistant_msg: str, tokens: int) -> Summary:
        combined = f"User: {user_msg}\nAssistant: {assistant_msg}"
        summary = self._create_summary(combined, tokens, SummaryTier.IMMEDIATE)
        self.immediate_summaries.append(summary)
        if len(self.immediate_summaries) > self.max_immediate:
            self._promote_to_recent()
        return summary

    def _create_summary(self, content: str, tokens: int, tier: str) -> Summary:
        import hashlib
        summary_text = self._compress(content)
        summary_tokens = int(len(summary_text.split()) * 1.3)
        return Summary(
            id=hashlib.sha256(f"{content}:{datetime.utcnow().isoformat()}".encode()).hexdigest()[:12],
            tier=tier,
            content=summary_text,
            source_tokens=tokens,
            summary_tokens=summary_tokens,
            compression_ratio=tokens / max(1, summary_tokens),
            key_points=self._extract_key_points(content),
            entities=self._extract_entities(content),
        )

    def _compress(self, text: str) -> str:
        sentences = text.split(". ")
        if len(sentences) <= 3:
            return text
        return ". ".join(sentences[:2] + [sentences[-1]]) + "."

    def _extract_key_points(self, text: str) -> list[str]:
        import re
        sentences = re.split(r"[.!?]+", text)
        return [s.strip() for s in sentences if len(s.strip()) > 20][:5]

    def _extract_entities(self, text: str) -> list[str]:
        import re
        words = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text)
        return list(set(words))[:10]

    def _promote_to_recent(self):
        if not self.immediate_summaries:
            return
        promoted = self.immediate_summaries.pop(0)
        promoted.tier = SummaryTier.RECENT
        self.recent_summaries.append(promoted)
        if len(self.recent_summaries) > self.max_recent:
            self._promote_to_session()

    def _promote_to_session(self):
        if not self.recent_summaries:
            return
        promoted = self.recent_summaries.pop(0)
        promoted.tier = SummaryTier.SESSION
        self.session_summaries.append(promoted)
        if len(self.session_summaries) > self.max_session:
            self._promote_to_historical()

    def _promote_to_historical(self):
        if not self.session_summaries:
            return
        promoted = self.session_summaries.pop(0)
        promoted.tier = SummaryTier.HISTORICAL
        self.historical_summaries.append(promoted)

    def create_semantic_summary(self, theme: str, related: list[Summary]) -> Summary:
        combined = f"Theme: {theme}\n" + "\n".join(s.content for s in related)
        summary = self._create_summary(combined, sum(s.source_tokens for s in related), SummaryTier.SEMANTIC)
        summary.metadata["theme"] = theme
        summary.metadata["source_summary_ids"] = [s.id for s in related]
        self.semantic_summaries.append(summary)
        return summary

    def get_context(self, max_tokens: int = 8000) -> str:
        parts = []
        token_count = 0
        for tier in [SummaryTier.IMMEDIATE, SummaryTier.RECENT, SummaryTier.SESSION, SummaryTier.SEMANTIC, SummaryTier.HISTORICAL]:
            summaries = getattr(self, f"{tier}_summaries")
            for summary in reversed(summaries):
                if token_count + summary.summary_tokens > max_tokens:
                    break
                parts.append(f"[{tier.upper()}] {summary.content}")
                token_count += summary.summary_tokens
        return "\n\n".join(reversed(parts))

    def get_all_summaries(self) -> list[Summary]:
        out = []
        for tier in [SummaryTier.IMMEDIATE, SummaryTier.RECENT, SummaryTier.SESSION, SummaryTier.HISTORICAL, SummaryTier.SEMANTIC]:
            out.extend(getattr(self, f"{tier}_summaries"))
        return out

    def get_stats(self) -> dict[str, Any]:
        return {
            "immediate": len(self.immediate_summaries),
            "recent": len(self.recent_summaries),
            "session": len(self.session_summaries),
            "historical": len(self.historical_summaries),
            "semantic": len(self.semantic_summaries),
            "total_tokens": sum(s.summary_tokens for s in self.get_all_summaries()),
        }

    def clear(self):
        self.immediate_summaries.clear()
        self.recent_summaries.clear()
        self.session_summaries.clear()
        self.historical_summaries.clear()
        self.semantic_summaries.clear()


class ContextWindow:
    def __init__(self, session_id: str = "default", budget_tokens: int = DEFAULT_BUDGET_TOKENS,
                 verbatim_tail: int = DEFAULT_VERBATIM_TAIL, storage_path: Path | None = None):
        self.session_id = session_id
        self.budget_tokens = budget_tokens
        self.verbatim_tail = verbatim_tail
        self.storage_path = storage_path
        self.messages: list[ContextMessage] = []
        self.summarizer = HierarchicalSummarizer()
        self._running_summary: str = ""
        self._running_summary_tokens: int = 0
        if storage_path and Path(storage_path).exists():
            self.load(storage_path)

    def append(self, role: str, content: str, metadata: dict[str, Any] | None = None) -> ContextMessage:
        message = ContextMessage(role=role, content=content, metadata=metadata or {})
        self.messages.append(message)
        self._maybe_compress()
        return message

    def get_messages(self) -> list[ContextMessage]:
        return list(self.messages)

    def get_messages_for_model(self) -> list[dict[str, str]]:
        self._maybe_compress()
        messages: list[dict[str, str]] = []
        if self._running_summary:
            messages.append({"role": "system", "content": f"[Compressed conversation memory]\n{self._running_summary}"})
        tail = self.messages[-self.verbatim_tail:] if self.verbatim_tail > 0 else []
        for message in tail:
            messages.append({"role": message.role, "content": message.content})
        return messages

    def get_total_tokens(self) -> int:
        return sum(m.tokens for m in self.messages) + self._running_summary_tokens

    def _maybe_compress(self):
        total = self.get_total_tokens()
        if total <= self.budget_tokens:
            return
        if len(self.messages) <= self.verbatim_tail:
            return
        older = self.messages[:-self.verbatim_tail] if self.verbatim_tail > 0 else self.messages[:]
        combined = "\n".join(f"{m.role}: {m.content}" for m in older)
        source_tokens = sum(m.tokens for m in older)
        summary = self.summarizer._create_summary(combined, source_tokens, SummaryTier.SESSION)
        self.messages = self.messages[-self.verbatim_tail:] if self.verbatim_tail > 0 else []
        self._running_summary = summary.content
        self._running_summary_tokens = summary.summary_tokens
        self.summarizer.session_summaries.append(summary)

    def save(self, path: Path | str | None = None):
        target = Path(path) if path is not None else self.storage_path
        if target is None:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "session_id": self.session_id,
            "messages": [{"role": m.role, "content": m.content, "tokens": m.tokens, "timestamp": m.timestamp, "metadata": m.metadata} for m in self.messages],
            "running_summary": self._running_summary,
            "running_summary_tokens": self._running_summary_tokens,
        }
        target.write_text(json.dumps(data, indent=2))

    def load(self, path):
        target = Path(path)
        if not target.exists():
            return
        data = json.loads(target.read_text())
        self.messages = [ContextMessage(role=m["role"], content=m["content"], tokens=m.get("tokens", 0), timestamp=m.get("timestamp"), metadata=m.get("metadata", {})) for m in data.get("messages", [])]
        self._running_summary = data.get("running_summary", "")
        self._running_summary_tokens = data.get("running_summary_tokens", 0)
