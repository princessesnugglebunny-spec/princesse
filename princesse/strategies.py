"""Alternative agent strategies for small models: structured reasoning, ensemble, progressive refinement."""

from __future__ import annotations

import asyncio
from typing import Any

from .agent import Agent
from .context import ContextWindow
from .llm import OpenAICompatibleProvider

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


