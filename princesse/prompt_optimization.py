"""Prompt optimization: compression, CoT, few-shot, self-consistency."""

from __future__ import annotations

class PromptCompressor:
    @staticmethod
    def compress(text: str, target_ratio: float = 0.6) -> str:
        # Remove redundant whitespace and repeated sentences
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        seen = set()
        out = []
        for ln in lines:
            if ln in seen:
                continue
            seen.add(ln)
            out.append(ln)
        text = "\n".join(out)
        # truncate to target ratio by chars (rough)
        if target_ratio < 1.0:
            keep = int(len(text) * target_ratio)
            if keep < len(text):
                text = text[:keep] + "..."
        return text

    @staticmethod
    def abbreviate_messages(messages: list[dict[str, str]], keep_last: int = 6) -> list[dict[str, str]]:
        if len(messages) <= keep_last + 1:
            return messages
        system = [m for m in messages if m.get("role") == "system"]
        tail = messages[-keep_last:]
        return system + tail


class ChainOfThought:
    @staticmethod
    def wrap(prompt: str, style: str = "step") -> str:
        if style == "step":
            return prompt + "\nLet's think step by step."
        if style == "react":
            return prompt + "\nThought: I should reason about this. Action: decide the next step."
        return prompt


class FewShotSelector:
    def __init__(self, examples: list[dict[str, str]]):
        self.examples = examples

    def select(self, query: str, k: int = 3) -> list[dict[str, str]]:
        # simple keyword overlap scoring
        ql = set(query.lower().split())
        scored = []
        for ex in self.examples:
            el = set((ex.get("input", "") + " " + ex.get("output", "")).lower().split())
            score = len(ql & el)
            scored.append((score, ex))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:k]]


class SelfConsistency:
    def __init__(self, provider, n: int = 3):
        self.provider = provider
        self.n = n

    async def run(self, messages: list[dict[str, str]]) -> str:
        import asyncio
        async def _one():
            data = await self.provider.complete(messages, None)
            return data["choices"][0]["message"].get("content", "")
        outs = await asyncio.gather(*[_one() for _ in range(self.n)], return_exceptions=True)
        outs = [o for o in outs if isinstance(o, str)]
        if not outs:
            return ""
        # majority vote by stripped answer
        from collections import Counter
        c = Counter(o.strip() for o in outs)
        return c.most_common(1)[0][0]
