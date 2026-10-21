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
from .small_model_booster import (SmallModelBooster, BoosterConfig, create_boosted_agent, FEW_SHOT_EXAMPLES)
from .strategies import StructuredReasoningAgent, EnsembleAgent, ProgressiveRefinementAgent
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
from .llm import LLMProvider, OpenAICompatibleProvider
from .config import Config, load_config
from .audit_log import AuditLog
from .security import CommandPolicy, PathEscapeError, SkillVerifier, safe_path
from .hooks import Hook, HookEngine, HookExecutor, HookMatch, TriggerSpec
from .rag import Indexer, Retriever, Chunker
from .transparency import EventBus, Event, TranscriptWriter
from .skill_catalogue import SkillCatalogue
from .mcp_catalogue import MCPCatalogue
from .bootstrap_install import EnvironmentBootstrap
from .reuse import ReuseAdvisor, PatternLibrary, extract_signatures
from .logging_setup import get_logger, configure as configure_logging

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
    "Config", "load_config", "AuditLog",
    "CommandPolicy", "PathEscapeError", "SkillVerifier", "safe_path",
    "Hook", "HookEngine", "HookExecutor", "HookMatch", "TriggerSpec",
    "Indexer", "Retriever", "Chunker",
    "EventBus", "Event", "TranscriptWriter",
    "SkillCatalogue", "MCPCatalogue", "EnvironmentBootstrap",
    "ReuseAdvisor", "PatternLibrary", "extract_signatures",
    "get_logger", "configure_logging",
    "ReflectionLoop", "register_git_tools", "register_lsp_tools", "lsp_diagnostics",
    "ToolResultCache", "MemoryConsolidator", "TDDCycle",
    "PromptCompressor", "ChainOfThought", "FewShotSelector", "SelfConsistency",
    "InferenceOptimizer", "ContextPruner",
    "ImportanceScorer", "SemanticDeduplicator", "TokenBudgetAllocator",
    "SlidingWindowCompressor", "OutputTruncator", "AdaptiveMaxTokens",
    "ConversationSummarizer", "RequestCoalescer", "EarlyStopper", "SpeculativePrefetcher",
    "SmallModelBooster", "BoosterConfig", "StructuredReasoningAgent", "EnsembleAgent",
    "ProgressiveRefinementAgent", "create_boosted_agent", "FEW_SHOT_EXAMPLES",
    "HFDownloader", "ModelsIni", "CodingAgent", "CodeResult", "solve_code",
]
