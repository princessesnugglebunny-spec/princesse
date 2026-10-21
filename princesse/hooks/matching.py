"""Semantic trigger matching: fuzzy, ordered, proximity-aware intent detection."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")

# Fuzzy matching is deliberately stricter than the trigger threshold: a loose
# ratio on short words produces garbage matches ("pytest" ~ "profiling").
FUZZY_MIN_RATIO = 0.82
FUZZY_MIN_WORD_LENGTH = 5

DEFAULT_SYNONYMS: dict[str, list[str]] = {
    "error": ["exception", "failure", "traceback", "crash", "bug", "stacktrace"],
    "fix": ["repair", "resolve", "patch", "correct", "heal"],
    "test": ["spec", "pytest", "unittest", "assertion"],
    "review": ["audit", "critique", "inspect", "evaluate"],
    "refactor": ["restructure", "cleanup", "clean", "tidy", "reorganize"],
    "debug": ["troubleshoot", "diagnose", "investigate"],
    "security": ["vulnerability", "cve", "exploit", "injection"],
    "performance": ["slow", "latency", "optimize", "profiling", "bottleneck"],
    "deploy": ["release", "ship", "publish", "rollout"],
    "research": ["investigate", "explore", "survey", "compare"],
    "document": ["docs", "readme", "docstring", "writeup"],
}


@dataclass
class TriggerSpec:
    words: list[str] = field(default_factory=list)
    order: str = "loose"            # "strict" | "loose"
    proximity: int = 60             # max token gap between matches
    threshold: float = 0.6          # fuzzy score gate
    min_matches: int = 1
    synonyms: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TriggerSpec":
        return cls(
            words=[str(w).lower() for w in data.get("words", [])],
            order=str(data.get("order", "loose")).lower(),
            proximity=int(data.get("proximity", 60)),
            threshold=float(data.get("threshold", 0.6)),
            min_matches=int(data.get("min_matches", 1)),
            synonyms={str(k).lower(): [str(v).lower() for v in vs]
                      for k, vs in (data.get("synonyms") or {}).items()},
        )


@dataclass
class Hook:
    id: str
    name: str = ""
    description: str = ""
    triggers: list[TriggerSpec] = field(default_factory=list)
    actions: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    source: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any], source: str = "") -> "Hook":
        return cls(
            id=str(data.get("id") or data.get("name", "hook")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            triggers=[TriggerSpec.from_dict(t) for t in data.get("triggers", [])],
            actions=dict(data.get("actions", {})),
            enabled=bool(data.get("enabled", True)),
            source=source,
        )


@dataclass
class HookMatch:
    hook: Hook | None
    score: float
    matched_words: list[str] = field(default_factory=list)
    positions: list[int] = field(default_factory=list)
    trigger_index: int = 0

    @property
    def hook_id(self) -> str:
        return self.hook.id if self.hook else ""

    def to_dict(self) -> dict[str, Any]:
        return {"hook": self.hook_id, "score": round(self.score, 3),
                "matched": self.matched_words, "positions": self.positions}


def tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(text)]


def _expand(words: list[str], synonyms: dict[str, list[str]]) -> dict[str, list[str]]:
    """Map every accepted surface form to its canonical trigger word.

    Only synonyms of the trigger's own words are considered: a synonym table
    entry for an unrelated word must never make the trigger fire.
    """
    out: dict[str, list[str]] = {}
    wanted = set(words)
    for w in words:
        out.setdefault(w, []).append(w)
        for s in synonyms.get(w, []):
            out.setdefault(s, []).append(w)
    for canonical, alts in synonyms.items():
        if canonical not in wanted:
            continue
        for alt in alts:
            out.setdefault(alt, []).append(canonical)
    return out


class HookEngine:
    """Loads hook packs and matches text against trigger specs."""

    def __init__(self, directories: list[Path | str] | None = None):
        self.hooks: dict[str, Hook] = {}
        self.directories = [Path(d) for d in (directories or [])]
        self.load_all()

    def load_all(self) -> int:
        self.hooks.clear()
        for directory in self.directories:
            if not directory or not Path(directory).exists():
                continue
            for yaml_file in sorted(Path(directory).rglob("*.yaml")):
                try:
                    payload = yaml.safe_load(yaml_file.read_text()) or {}
                except Exception:
                    continue
                entries = payload.get("hooks", payload if isinstance(payload, list) else [])
                if isinstance(entries, dict):
                    entries = [entries]
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    hook = Hook.from_dict(entry, source=str(yaml_file))
                    self.hooks[hook.id] = hook
        return len(self.hooks)

    def add(self, hook: Hook) -> Hook:
        self.hooks[hook.id] = hook
        return hook

    def list_all(self) -> list[Hook]:
        return list(self.hooks.values())

    def match(self, text: str, top: int = 5) -> list[HookMatch]:
        tokens = tokenize(text)
        results: list[HookMatch] = []
        for hook in self.hooks.values():
            if not hook.enabled:
                continue
            best: HookMatch | None = None
            for idx, trigger in enumerate(hook.triggers):
                m = self._match_trigger(trigger, tokens)
                if m and (best is None or m.score > best.score):
                    m.trigger_index = idx
                    best = m
            if best is not None:
                best.hook = hook
                results.append(best)
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top]

    def _match_trigger(self, trigger: TriggerSpec, tokens: list[str]) -> HookMatch | None:
        if not trigger.words:
            return None
        accepted = _expand(trigger.words, {**DEFAULT_SYNONYMS, **trigger.synonyms})
        positions: dict[str, int] = {}
        matched_canonical: list[str] = []
        fuzzy_hits = 0

        for i, tok in enumerate(tokens):
            if tok in accepted:
                canonical = accepted[tok][0]
                if canonical not in positions:
                    positions[canonical] = i
                    matched_canonical.append(canonical)
                continue
            # fuzzy: find a close trigger word
            best_ratio, best_word = 0.0, ""
            for surface in accepted:
                if len(tok) < FUZZY_MIN_WORD_LENGTH or len(surface) < FUZZY_MIN_WORD_LENGTH:
                    continue
                ratio = difflib.SequenceMatcher(None, tok, surface).ratio()
                if ratio > best_ratio:
                    best_ratio, best_word = ratio, surface
            if best_ratio >= FUZZY_MIN_RATIO and best_word not in positions:
                positions[best_word] = i
                matched_canonical.append(best_word)
                fuzzy_hits += 1

        matched_count = len(positions)
        if matched_count < max(1, trigger.min_matches):
            return None

        ordered = sorted(positions.values())
        if trigger.order == "strict":
            canonical_order = [w for w, _ in sorted(positions.items(), key=lambda kv: kv[1])]
            expected = [w for w in trigger.words if w in canonical_order]
            if len(expected) > 1 and canonical_order != expected:
                return None

        if len(ordered) > 1:
            gaps = [ordered[i + 1] - ordered[i] for i in range(len(ordered) - 1)]
            if max(gaps) > trigger.proximity:
                return None

        # Score reflects how well the trigger fired, not how many alternative
        # words the trigger happens to list: one exact hit on a min_matches=1
        # trigger is a full match.
        required = max(1, trigger.min_matches)
        score = min(1.0, matched_count / required)
        if fuzzy_hits:
            score *= (1.0 - 0.1 * fuzzy_hits)
        score = round(score, 4)
        if score < trigger.threshold:
            return None
        return HookMatch(hook=None, score=score, matched_words=sorted(positions.keys()), positions=ordered)


