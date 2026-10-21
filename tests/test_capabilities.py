from princesse.capabilities import pii_redact, complexity_evaluate, release_tag, canary_evaluate, knowledge_extract

def test_pii_redact():
    r = pii_redact("email a@b.com phone 123-456-7890")
    assert "REDACTED" in r["redacted_text"]
    assert r["findings"].get("email") == 1

def test_release_tag():
    assert release_tag("1.2.3", "patch") == "1.2.4"
    assert release_tag("1.2.3", "minor") == "1.3.0"
    assert release_tag("1.2.3", "major") == "2.0.0"

def test_canary():
    r = canary_evaluate(10.0, 10.2, 0.05)
    assert r["promote"] is True

def test_knowledge_extract(tmp_path):
    p = tmp_path/"x.py"
    p.write_text("class A:\n    pass\ndef f():\n    pass\nimport os\n")
    r = knowledge_extract(str(p))
    assert "A" in r["classes"]
    assert "f" in r["functions"]
