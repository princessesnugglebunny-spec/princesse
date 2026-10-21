"""Parameter sweep and benchmark harness for llama.cpp-style servers."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class BenchResult:
    params: dict[str, Any]
    throughput_tok_s: float
    latency_ms: float
    error: str | None = None


class ParamSweep:
    def __init__(self, runner: Callable[[dict[str, Any]], float]):
        self.runner = runner

    def run(self, grid: dict[str, list[Any]]) -> list[BenchResult]:
        keys = list(grid.keys())
        results: list[BenchResult] = []

        def cartesian(idx, current):
            if idx == len(keys):
                params = dict(current)
                t0 = time.monotonic()
                try:
                    tps = self.runner(params)
                    results.append(BenchResult(params=params, throughput_tok_s=tps,
                                            latency_ms=(time.monotonic() - t0) * 1000))
                except Exception as e:
                    results.append(BenchResult(params=params, throughput_tok_s=0.0,
                                            latency_ms=(time.monotonic() - t0) * 1000, error=str(e)))
                return
            for v in grid[keys[idx]]:
                current[keys[idx]] = v
                cartesian(idx + 1, current)

        cartesian(0, {})
        results.sort(key=lambda r: r.throughput_tok_s, reverse=True)
        return results

    @staticmethod
    def best(results: list[BenchResult]) -> BenchResult | None:
        ok = [r for r in results if r.error is None]
        if not ok:
            return None
        return max(ok, key=lambda r: r.throughput_tok_s)


class BenchmarkHarness:
    def __init__(self, call_fn: Callable[[str], str]):
        self.call_fn = call_fn

    def run(self, prompts: list[str], rounds: int = 1) -> dict[str, Any]:
        latencies = []
        outputs = []
        for _ in range(rounds):
            for p in prompts:
                t0 = time.monotonic()
                try:
                    out = self.call_fn(p)
                    outputs.append(out)
                except Exception as e:
                    outputs.append(f"ERROR: {e}")
                latencies.append((time.monotonic() - t0) * 1000)
        return {
            "rounds": rounds,
            "prompts": len(prompts),
            "median_latency_ms": statistics.median(latencies) if latencies else 0.0,
            "mean_latency_ms": statistics.fmean(latencies) if latencies else 0.0,
            "outputs": outputs,
        }
