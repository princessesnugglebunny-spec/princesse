from princesse.context_optimization import (ImportanceScorer, SemanticDeduplicator, TokenBudgetAllocator,
    SlidingWindowCompressor, OutputTruncator, AdaptiveMaxTokens, ConversationSummarizer)
from princesse.llm_optimization import EarlyStopper, SpeculativePrefetcher

def test_importance_scorer():
    m = {"role": "user", "content": "hello world"}
    s = ImportanceScorer.score(m, "hello", 5, 10)
    assert 0 <= s <= 2

def test_semantic_dedup():
    msgs = [{"content": "a"}, {"content": "a"}, {"content": "b"}]
    out = SemanticDeduplicator.dedup(msgs)
    assert len(out) == 2

def test_token_budget_allocator():
    a = TokenBudgetAllocator(1000)
    r = a.allocate({"sys": 2, "user": 1})
    assert r["sys"] + r["user"] <= 1001

def test_output_truncator():
    text = "a" * 5000
    out = OutputTruncator.truncate_tool_output(text, max_chars=100)
    assert "truncated" in out

def test_adaptive_max_tokens():
    assert AdaptiveMaxTokens.for_task("hi") == 512
    assert AdaptiveMaxTokens.for_task("a " * 60) > 512

def test_early_stopper():
    assert EarlyStopper.should_stop("This is a complete answer with enough length.") is True
    assert EarlyStopper.should_stop("short") is False

def test_speculative_prefetcher():
    ts = SpeculativePrefetcher.predict("fix the git diff in the file")
    assert "git_status" in ts or "git_diff" in ts or "read_file" in ts
