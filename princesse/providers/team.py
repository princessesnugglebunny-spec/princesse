"""Model teaming: capability routing, ensemble voting, and debate."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from ..llm import OpenAICompatibleProvider
from .cli_bridge import CLIProvider
from .registry import ProviderSpec

CAPABILITY_TAGS = ["code", "reasoning", "summarize", "tool_call", "cheap", "fast", "general"]


@dataclass
class TeamMember:
    name: str
    provider: Any
    tags: list[str] = field(default_factory=list)
    model: str = ""

    def supports(self, tag: str) -> bool:
        return tag in self.tags


def _guess_tags(model_id: str, description: str = "") -> list[str]:
    hay = f"{model_id} {description}".lower()
    tags = []
    if any(k in hay for k in ("code", "coder", "program", "starcoder", "deepseek-coder")):
        tags.append("code")
    if any(k in hay for k in ("reason", "thinker", "r1", "qwq", "distill")):
        tags.append("reasoning")
    if any(k in hay for k in ("summar", "mini", "haiku", "flash", "small")):
        tags.append("summarize")
        tags.append("cheap")
        tags.append("fast")
    if "tool" in hay or "hermes" in hay or "function" in hay:
        tags.append("tool_call")
    if not tags:
        tags.append("general")
    return tags


class ModelTeam:
    """Coordinates several providers/models as one logical teammate."""

    def __init__(self, members: list[TeamMember] | None = None):
        self.members: list[TeamMember] = members or []

    def add(self, name: str, provider: Any, tags: list[str] | None = None, model: str = "") -> TeamMember:
        member = TeamMember(name=name, provider=provider, tags=tags or ["general"], model=model)
        self.members.append(member)
        return member

    def add_provider_spec(self, spec: ProviderSpec, api_key: str = "", model: str = "",
                          tags: list[str] | None = None) -> TeamMember:
        if spec.cli_command:
            provider = CLIProvider(spec=spec, model=model)
        else:
            provider = OpenAICompatibleProvider(base_url=spec.base_url, api_key=api_key, model=model)
        return self.add(spec.name, provider, tags or _guess_tags(model, spec.notes), model)

    def route(self, task: str, strategy: str = "capability") -> TeamMember | None:
        """Pick the best member for a task."""
        if not self.members:
            return None
        if strategy == "roundrobin":
            return self.members[0]
        ql = set(task.lower().split())
        best = None
        best_score = -1.0
        for member in self.members:
            score = 0.0
            if member.supports("code") and ("code" in ql or "function" in ql or "implement" in ql):
                score += 3
            if member.supports("reasoning") and ("why" in ql or "explain" in ql or "plan" in ql):
                score += 3
            if member.supports("summarize") and ("summar" in ql or "tldr" in ql):
                score += 3
            if member.supports("tool_call") and ql & {"read", "search", "run", "edit", "fetch"}:
                score += 2
            if member.supports("cheap") and len(ql) > 40:
                score += 1
            if score > best_score:
                best_score = score
                best = member
        return best or self.members[0]

    async def ask(self, task: str, member: TeamMember, tools: list[dict] | None = None) -> str:
        data = await member.provider.complete([{"role": "user", "content": task}], tools)
        if hasattr(member.provider, "parse_response"):
            content, _ = member.provider.parse_response(data)
        else:
            content = data["choices"][0]["message"].get("content", "")
        return content

    async def ensemble(self, task: str, n: int = 3, tools: list[dict] | None = None) -> dict[str, Any]:
        """Run n members in parallel and take the majority answer."""
        if not self.members:
            return {"answer": "", "agreement": 0.0, "answers": []}
        picks = [self.members[i % len(self.members)] for i in range(n)]

        async def _run(member: TeamMember) -> str:
            try:
                return await self.ask(task, member, tools)
            except Exception as e:
                return f"ERROR: {e}"

        answers = await asyncio.gather(*[_run(m) for m in picks])
        from collections import Counter
        normalized = [a.strip() for a in answers if not a.startswith("ERROR")]
        if not normalized:
            return {"answer": answers[0] if answers else "", "agreement": 0.0, "answers": answers}
        counts = Counter(normalized)
        best, votes = counts.most_common(1)[0]
        return {"answer": best, "agreement": votes / len(picks), "answers": answers,
                "per_member": [m.name for m in picks]}

    async def debate(self, task: str, n: int = 3, rounds: int = 1) -> dict[str, Any]:
        """Members propose, critique each other, and a synthesizer picks the best."""
        if not self.members:
            return {"answer": "", "rounds": []}
        picks = [self.members[i % len(self.members)] for i in range(n)]
        proposals = await asyncio.gather(*[self.ask(task, m) for m in picks])
        proposals = [p if isinstance(p, str) else str(p) for p in proposals]

        history = [{"proposals": proposals}]
        current = proposals
        for _ in range(rounds):
            critiques = await asyncio.gather(*[
                self.ask(f"Critique this answer to '{task}':\n\n{current[i]}\n\n"
                         f"Other answers:\n" + "\n".join(f"- {p}" for j, p in enumerate(current) if j != i),
                         m)
                for i, m in enumerate(picks)
            ])
            critiques = [c if isinstance(c, str) else str(c) for c in critiques]
            history.append({"critiques": critiques})
            current = [
                f"Answer: {proposals[i]}\nCritique to address: {critiques[i]}"
                for i in range(len(proposals))
            ]

        synthesizer = self.members[0]
        final = await self.ask(
            f"Original task: {task}\n\nCandidate answers and critiques:\n" +
            "\n\n".join(f"--- Candidate {i+1} ---\n{current[i]}" for i in range(len(current))) +
            "\n\nProduce the single best final answer.",
            synthesizer)
        return {"answer": final if isinstance(final, str) else str(final), "rounds": history,
                "per_member": [m.name for m in picks]}
