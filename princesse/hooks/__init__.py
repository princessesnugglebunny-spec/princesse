"""Semantic trigger hooks: fuzzy, order-flexible intent matching that acts before the LLM does."""

from .matching import (DEFAULT_SYNONYMS, Hook, HookEngine, HookMatch, TriggerSpec, tokenize)
from .executor import HookExecutor, HookOutcome

__all__ = [
    "DEFAULT_SYNONYMS", "Hook", "HookEngine", "HookMatch", "TriggerSpec", "tokenize",
    "HookExecutor", "HookOutcome",
]
