from princesse.prompt_optimization import PromptCompressor, ChainOfThought, FewShotSelector
from princesse.tool_cache import ToolResultCache
from princesse.context_pruning import ContextPruner
from princesse.context import ContextWindow

def test_prompt_compressor():
    text = "hello world\nhello world\n\nfoo bar"
    out = PromptCompressor.compress(text, 1.0)
    assert "hello world" in out
    assert out.count("hello world") == 1

def test_cot():
    p = ChainOfThought.wrap("solve x", "step")
    assert "step by step" in p

def test_fewshot():
    exs = [{"input": "add numbers", "output": "sum"}, {"input": "greet user", "output": "hi"}]
    sel = FewShotSelector(exs)
    r = sel.select("add two numbers", k=1)
    assert r[0]["output"] == "sum"

def test_context_pruner():
    cw = ContextWindow(budget_tokens=1000, verbatim_tail=2)
    for i in range(10):
        cw.append("user", f"message {i}")
    msgs = ContextPruner.prune(cw, "message 9", max_messages=4)
    assert len(msgs) <= 4
