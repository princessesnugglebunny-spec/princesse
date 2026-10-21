from princesse.context import ContextWindow, HierarchicalSummarizer

def test_context_window_basic():
    cw = ContextWindow(budget_tokens=100, verbatim_tail=2)
    cw.append("user", "hello world")
    cw.append("assistant", "hi there")
    msgs = cw.get_messages_for_model()
    assert any(m["content"] == "hello world" for m in msgs)

def test_compression_triggers():
    cw = ContextWindow(budget_tokens=20, verbatim_tail=1)
    for i in range(10):
        cw.append("user", "this is a longer message number %d" % i)
        cw.append("assistant", "acknowledged message %d" % i)
    msgs = cw.get_messages_for_model()
    # should have compressed summary + tail
    assert len(msgs) <= 3
    assert any("Compressed" in m["content"] for m in msgs)

def test_hierarchical_summarizer():
    s = HierarchicalSummarizer()
    sm = s.add_interaction("user question", "assistant answer", 50)
    assert sm.tier == "immediate"
    assert s.get_stats()["immediate"] == 1
