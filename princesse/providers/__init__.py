"""Provider layer: registry, catalogue, CLI bridge, and model teaming."""

from .registry import BUILTIN_PROVIDERS, ProviderRegistry, ProviderSpec
from .catalogue import Catalogue, CatalogueManager, ModelInfo
from .cli_bridge import CLIProvider
from .team import ModelTeam, TeamMember
from ..llm import LLMProvider, OpenAICompatibleProvider

__all__ = [
    "BUILTIN_PROVIDERS", "ProviderRegistry", "ProviderSpec",
    "Catalogue", "CatalogueManager", "ModelInfo",
    "CLIProvider", "ModelTeam", "TeamMember", "OpenAICompatibleProvider", "LLMProvider",
]
