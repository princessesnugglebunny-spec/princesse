"""Small Model Booster: techniques to make sub-7B models competitive with larger models."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .agent import Agent
from .prompt_optimization import ChainOfThought, FewShotSelector, SelfConsistency
from .logging_setup import get_logger, log_swallowed
from .strategies import EnsembleAgent, ProgressiveRefinementAgent, StructuredReasoningAgent

logger = get_logger("small_model_booster")

__all__ = ["SmallModelBooster", "BoosterConfig", "DEFAULT_BOOSTER_CONFIG", "FEW_SHOT_EXAMPLES",
           "create_boosted_agent", "EnsembleAgent", "ProgressiveRefinementAgent",
           "StructuredReasoningAgent"]


@dataclass
class BoosterConfig:
    use_cot: bool = True
    cot_style: str = "step"
    use_few_shot: bool = True
    few_shot_k: int = 3
    use_self_consistency: bool = False
    consistency_n: int = 3
    use_reflection: bool = True
    max_reflections: int = 2
    use_verification: bool = True
    verify_temperature: float = 0.0
    use_prompt_compression: bool = True
    use_tool_output_truncation: bool = True
    max_tool_output_chars: int = 1500


DEFAULT_BOOSTER_CONFIG = BoosterConfig()


FEW_SHOT_EXAMPLES = [
    {"input": "Read file and summarize", "output": "read_file -> analyze -> summarize"},
    {"input": "Fix failing test", "output": "run tests -> read failing test -> read source -> edit -> rerun"},
    {"input": "Create new feature", "output": "plan -> write tests -> implement -> verify -> refactor"},
    {"input": "Debug error", "output": "reproduce -> trace -> hypothesize -> fix -> test"},
    {"input": "Refactor code", "output": "analyze -> write tests -> incrementally change -> verify"},
]


class SmallModelBooster:
    """Wraps an agent with techniques that boost small model performance."""
    
    def __init__(self, agent: Agent, config: BoosterConfig = DEFAULT_BOOSTER_CONFIG,
                 few_shot_examples: list[dict[str, str]] | None = None):
        self.agent = agent
        self.config = config
        self.few_shot = FewShotSelector(few_shot_examples or FEW_SHOT_EXAMPLES)
        self.consistency = SelfConsistency(agent.provider, n=config.consistency_n) if config.use_self_consistency else None
        self.reflection_count = 0
    
    def enhance_system_prompt(self, base_prompt: str) -> str:
        """Inject CoT and structured reasoning into system prompt."""
        if not self.config.use_cot:
            return base_prompt
        
        enhanced = base_prompt + "\n\n" + ChainOfThought.wrap("", self.config.cot_style)
        
        if self.config.use_few_shot:
            examples = self.few_shot.select("general", self.config.few_shot_k)
            if examples:
                enhanced += "\n\nExamples:\n"
                for ex in examples:
                    enhanced += f"Input: {ex.get('input', '')}\nOutput: {ex.get('output', '')}\n\n"
        
        enhanced += (
            "\nGuidelines for small model reasoning:\n"
            "- Break complex tasks into atomic steps\n"
            "- Explicitly state your reasoning before acting\n"
            "- Prefer simple, verifiable actions\n"
            "- After each tool result, summarize what you learned\n"
            "- If uncertain, request clarification or run a check\n"
        )
        return enhanced
    
    async def boosted_run(self, goal: str) -> Any:
        """Run with all boosting techniques applied."""
        # 1. Enhance system prompt
        original_prompt = self.agent.system_prompt
        self.agent.system_prompt = self.enhance_system_prompt(original_prompt)
        
        try:
            # 2. Run with self-consistency if enabled
            if self.config.use_self_consistency and self.consistency:
                # Run the agent, then take a majority vote over independent samples
                result = await self.agent.run(goal, use_optimizations=False)
                messages = ([{"role": "system", "content": self.agent.system_prompt}]
                            + self.agent.context.get_messages_for_model())
                consensus = await self.consistency.run(messages)
                if consensus:
                    result.final_answer = consensus
                
                if self.config.use_reflection and self.config.max_reflections > 0:
                    result = await self._reflect_and_improve(goal, result)
                
                return result
            
            # 3. Standard boosted run
            result = await self.agent.run(goal, use_optimizations=True)
            
            # 4. Reflection loop
            if self.config.use_reflection and self.config.max_reflections > 0:
                result = await self._reflect_and_improve(goal, result)
            
            # 5. Verification pass
            if self.config.use_verification:
                result = await self._verify_answer(goal, result)
            
            return result
            
        finally:
            self.agent.system_prompt = original_prompt
    
    async def _reflect_and_improve(self, goal: str, result: Any) -> Any:
        from .reflection import ReflectionLoop
        reflection = ReflectionLoop(self.agent, max_reflections=self.config.max_reflections)
        return await reflection.run(goal)
    
    async def _verify_answer(self, goal: str, result: Any) -> Any:
        """Run a low-temperature verification pass."""
        if result.final_answer.startswith("Error") or result.final_answer.startswith("Reached"):
            return result
        
        verify_prompt = (
            f"Verify this answer is correct and complete.\n"
            f"Goal: {goal}\nAnswer: {result.final_answer}\n"
            f"Respond with JSON: {{\"verified\": true/false, \"issues\": \"...\", \"improved\": \"...\"}}"
        )
        
        try:
            data = await self.agent.provider.complete(
                [{"role": "system", "content": "You are a strict verifier."},
                 {"role": "user", "content": verify_prompt}],
                None,
                max_tokens=512,
                temperature=self.config.verify_temperature
            )
            content = data["choices"][0]["message"].get("content", "")
            parsed = json.loads(content)
            if not parsed.get("verified", True) and parsed.get("improved"):
                result.final_answer = parsed["improved"]
        except Exception as e:
            log_swallowed(logger, "verification pass failed", e, goal=goal[:120])
        return result


def create_boosted_agent(provider, tools, config: BoosterConfig | None = None) -> SmallModelBooster:
    """Factory for a fully boosted small-model agent."""
    agent = Agent(provider=provider, tools=tools, system_prompt="You are a careful, step-by-step reasoning agent.")
    return SmallModelBooster(agent, config or BoosterConfig())
