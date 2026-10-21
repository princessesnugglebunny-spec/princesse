from princesse.optimize import ParamSweep, BenchmarkHarness

def test_param_sweep():
    def runner(params):
        return params["a"] * 2 + params["b"]
    sweep = ParamSweep(runner)
    results = sweep.run({"a": [1, 2], "b": [0, 1]})
    assert len(results) == 4
    b = sweep.best(results)
    assert b is not None
    assert b.throughput_tok_s == 5.0

def test_benchmark():
    h = BenchmarkHarness(lambda p: p.upper())
    r = h.run(["a", "b"], rounds=2)
    assert r["prompts"] == 2
    assert r["rounds"] == 2
    assert len(r["outputs"]) == 4
