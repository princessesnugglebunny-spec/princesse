"""princesse: an original agent runtime distilled from multiple references."""

__version__ = "0.1.0"

from .context import ContextWindow, HierarchicalSummarizer, ContextMessage, Summary, SummaryTier
from .tools import ToolRegistry, ToolEntry, ToolParameter, SandboxSpec, ToolCategory
from .memory import MemoryStore, MemoryNudge
from .agent import Agent, AgentLoop, AgentResult
from .profiles import AgentProfile, load_profile, load_profiles
from .prompts import PromptAssembler
from .models import GGUFMetadata, ModelProfile, probe_gguf, autoconfig, LlamaServer
from .optimize import ParamSweep, BenchmarkHarness, BenchResult
from .orchestration import TaskPlanner, MultiAgentOrchestrator, MultiAgentResult, PlanStep
from .skills import Skill, SkillRegistry, parse_skill
from .skill_download import SkillDownloader
from .tool_synthesis import ToolSynthesizer
from .codebase_explore import CodebaseExplorer, extract_symbols
from .reflection import ReflectionLoop
from .git_tools import register_git_tools
from .lsp_tool import register_lsp_tools, lsp_diagnostics
from .tool_cache import ToolResultCache
from .memory_consolidation import MemoryConsolidator
from .tdd import TDDCycle
from .prompt_optimization import PromptCompressor, ChainOfThought, FewShotSelector, SelfConsistency
from .inference import InferenceOptimizer
from .context_pruning import ContextPruner
from .context_optimization import (ImportanceScorer, SemanticDeduplicator, TokenBudgetAllocator,
    SlidingWindowCompressor, OutputTruncator, AdaptiveMaxTokens, ConversationSummarizer)
from .llm_optimization import RequestCoalescer, EarlyStopper, SpeculativePrefetcher
from .small_model_booster import (SmallModelBooster, BoosterConfig, StructuredReasoningAgent,
    EnsembleAgent, ProgressiveRefinementAgent, create_boosted_agent, FEW_SHOT_EXAMPLES)
from .hf_download import HFDownloader
from .models_ini import ModelsIni
from .coding_agent import CodingAgent, CodeResult, solve_code
from .capabilities import register_capability_tools
from .execution import register_execution_tools
from .browser import register_browser_tools
from .bootstrap import register_default_tools
from .delegation import DelegationManager
from .learning import LearningLoop
from .mcp_client import MCPClient, MCPRegistry
from .providers import LLMProvider, OpenAICompatibleProvider

__all__ = [
    "ContextWindow", "HierarchicalSummarizer", "ContextMessage", "Summary", "SummaryTier",
    "ToolRegistry", "ToolEntry", "ToolParameter", "SandboxSpec", "ToolCategory",
    "MemoryStore", "MemoryNudge", "Agent", "AgentLoop", "AgentResult",
    "AgentProfile", "load_profile", "load_profiles", "PromptAssembler",
    "GGUFMetadata", "ModelProfile", "probe_gguf", "autoconfig", "LlamaServer",
    "ParamSweep", "BenchmarkHarness", "BenchResult",
    "TaskPlanner", "MultiAgentOrchestrator", "MultiAgentResult", "PlanStep",
    "Skill", "SkillRegistry", "parse_skill", "SkillDownloader", "ToolSynthesizer",
    "CodebaseExplorer", "extract_symbols", "register_capability_tools",
    "register_execution_tools", "register_browser_tools", "register_default_tools",
    "DelegationManager", "LearningLoop", "MCPClient", "MCPRegistry",
    "LLMProvider", "OpenAICompatibleProvider",
]
