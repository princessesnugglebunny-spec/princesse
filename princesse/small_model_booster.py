"""Small Model Booster: techniques to make sub-7B models competitive with larger models."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from .agent import Agent
from .llm import OpenAICompatibleProvider
from .prompt_optimization import ChainOfThought, FewShotSelector, SelfConsistency
from .context import ContextWindow


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


# Built-in few-shot examples for common patterns
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
        except Exception:
            pass
        return result


class StructuredReasoningAgent:
    """Agent that forces structured reasoning: Plan -> Act -> Observe -> Reflect."""
    
    def __init__(self, provider, tools, system_prompt: str = ""):
        self.provider = provider
        self.tools = tools
        self.base_prompt = system_prompt or "You are a structured reasoning agent."
    
    async def solve(self, goal: str, max_steps: int = 10) -> dict[str, Any]:
        context = ContextWindow()
        context.append("user", goal)
        
        # Phase 1: Planning
        plan = await self._plan(goal, context)
        
        # Phase 2: Execute steps
        results = []
        for i, step in enumerate(plan):
            if i >= max_steps:
                break
            obs = await self._act(step, context)
            results.append({"step": step, "observation": obs})
            
            # Check if done
            if self._is_done(obs):
                break
        
        # Phase 3: Synthesize
        final = await self._synthesize(goal, results, context)
        return {"plan": plan, "results": results, "final": final}
    
    async def _plan(self, goal: str, context: ContextWindow) -> list[str]:
        prompt = (
            f"{self.base_prompt}\n\n"
            f"Goal: {goal}\n\n"
            f"Create a step-by-step plan. Each step must be a single atomic action.\n"
            f"Format: 1. action - expected outcome\n"
        )
        data = await self.provider.complete(
            [{"role": "system", "content": prompt}],
            None, max_tokens=512, temperature=0.2
        )
        content = data["choices"][0]["message"].get("content", "")
        # Parse numbered list
        steps = []
        for line in content.splitlines():
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-")):
                steps.append(line.split(".", 1)[-1].strip())
        return steps or [goal]
    
    async def _act(self, step: str, context: ContextWindow) -> str:
        prompt = f"Execute: {step}\nAvailable tools: {list(self.tools._tools.keys())}\n"
        context.append("user", prompt)
        
        data = await self.provider.complete(
            [{"role": "system", "content": self.base_prompt}] + context.get_messages_for_model(),
            self.tools.to_openai_tools(),
            max_tokens=256
        )
        content, calls = self.provider.parse_response(data)
        
        if calls:
            for call in calls:
                try:
                    result = await self.tools.execute(call["name"], call["arguments"])
                    context.append("tool", str(result)[:2000], metadata={"tool": call["name"]})
                    return str(result)[:2000]
                except Exception as e:
                    return f"Error: {e}"
        
        context.append("assistant", content)
        return content
    
    def _is_done(self, observation: str) -> bool:
        obs = observation.lower()
        return any(kw in obs for kw in ["done", "complete", "finished", "solved", "success"])
    
    async def _synthesize(self, goal: str, results: list, context: ContextWindow) -> str:
        summary = "\n".join(f"Step: {r['step']}\nResult: {r['observation'][:200]}" for r in results)
        prompt = f"Goal: {goal}\n\nExecution trace:\n{summary}\n\nProvide final answer."
        
        data = await self.provider.complete(
            [{"role": "system", "content": self.base_prompt},
             {"role": "user", "content": prompt}],
            None, max_tokens=1024, temperature=0.1
        )
        return data["choices"][0]["message"].get("content", "")


class EnsembleAgent:
    """Run multiple small models and aggregate (requires multiple endpoints)."""
    
    def __init__(self, providers: list[OpenAICompatibleProvider], tools):
        self.providers = providers
        self.tools = tools
    
    async def run(self, goal: str) -> dict[str, Any]:
        agents = [Agent(p, self.tools, system_prompt="You are a helpful agent.") for p in self.providers]
        results = await asyncio.gather(*[a.run(goal) for a in agents])
        
        # Aggregate by majority vote on tool calls and final answer
        answers = [r.final_answer for r in results]
        from collections import Counter
        # Simple majority on final answer (exact match)
        vote = Counter(a.strip() for a in answers)
        best_answer = vote.most_common(1)[0][0]
        
        # Combine tool calls
        all_calls = []
        for r in results:
            all_calls.extend(r.tool_calls)
        
        return {
            "answer": best_answer,
            "individual_answers": answers,
            "tool_calls": all_calls,
            "agreement": vote.most_common(1)[0][1] / len(answers)
        }


class ProgressiveRefinementAgent:
    """Iteratively refine answer with increasing depth."""
    
    def __init__(self, provider, tools, system_prompt: str = ""):
        self.provider = provider
        self.tools = tools
        self.base_prompt = system_prompt
    
    async def run(self, goal: str, rounds: int = 3) -> str:
        current_answer = ""
        
        for round_num in range(rounds):
            if round_num == 0:
                prompt = f"Quick answer for: {goal}"
            else:
                prompt = (
                    f"Refine this answer for: {goal}\n"
                    f"Previous: {current_answer}\n"
                    f"Add detail, fix errors, be more precise."
                )
            
            data = await self.provider.complete(
                [{"role": "system", "content": self.base_prompt},
                 {"role": "user", "content": prompt}],
                self.tools.to_openai_tools() if round_num > 0 else None,
                max_tokens=512 * (round_num + 1)
            )
            content, calls = self.provider.parse_response(data)
            
            if calls:
                for call in calls:
                    try:
                        result = await self.tools.execute(call["name"], call["arguments"])
                        current_answer += f"\nTool {call['name']}: {result}"
                    except Exception as e:
                        current_answer += f"\nError: {e}"
            
            current_answer = content or current_answer
            
            # Early stop if answer seems complete
            if self._looks_complete(current_answer, goal):
                break
        
        return current_answer
    
    def _looks_complete(self, answer: str, goal: str) -> bool:
        if len(answer) < 50:
            return False
        # Check if key terms from goal are addressed
        goal_words = set(goal.lower().split())
        answer_words = set(answer.lower().split())
        coverage = len(goal_words & answer_words) / max(1, len(goal_words))
        return coverage > 0.5


def create_boosted_agent(provider, tools, config: BoosterConfig | None = None) -> SmallModelBooster:
    """Factory for a fully boosted small-model agent."""
    agent = Agent(provider=provider, tools=tools, system_prompt="You are a careful, step-by-step reasoning agent.")
    return SmallModelBooster(agent, config or BoosterConfig())
